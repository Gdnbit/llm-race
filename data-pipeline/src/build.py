"""Pipeline orchestrator — fetch all sources, merge, write dataset.json.

Two-phase orchestration:
  1. **Anchor phase** — runs `SourceAdapter`s in parallel (currently only
     OpenRouter). Produces full `Model` records with canonical IDs.
  2. **Enrichment phase** — runs `EnrichmentAdapter`s in parallel
     (currently LMArena; future: Vectara HHEM, Artificial Analysis, etc.).
     Each produces `EnrichmentRecord`s keyed by source-specific names.
  3. **Merge** — `merger.merge_enrichments` aligns and applies enrichment
     records onto the anchor models, recomputes tiers, and produces the
     final `Dataset`.

Adding a new enrichment source:
  - Implement `EnrichmentAdapter` (see `sources/lmarena.py` as the
    reference).
  - Append to `_enrichment_adapters()` below.
  - No changes needed in this orchestrator.

Usage:
    python -m src.build
    python -m src.build --pretty       # pretty-print the JSON output
    python -m src.build --dry-run      # fetch but don't write
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

import structlog

from .config import config
from .merger import (
    EnrichmentRecord,
    build_enrichment_source_meta,
    merge_enrichments,
)
from .models import Dataset, Model, SourceMeta
from .sources.base import EnrichmentAdapter, SourceAdapter
from .sources.lmarena import LMArenaAdapter
from .sources.openrouter import OpenRouterAdapter


def _setup_logging() -> None:
    level = getattr(logging, config.log_level, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
    )
    # Redirected asset URLs can contain temporary access signatures.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(
                colors=False, exception_formatter=structlog.dev.plain_traceback
            ),
        ],
    )


logger = structlog.get_logger(__name__)


# ────────────────────────── Adapter registry ──────────────────────────


def _anchor_adapters() -> list[SourceAdapter]:
    """Anchor sources — produce canonical `Model` records.

    Currently only OpenRouter, which is the source of truth for canonical IDs.
    """
    return [OpenRouterAdapter()]


def _enrichment_adapters() -> list[EnrichmentAdapter]:
    """Enrichment sources — produce partial-signal `EnrichmentRecord`s.

    Step 3 active: LMArena.
    Future: VectaraHHEM, ArtificialAnalysis, HuggingFaceLeaderboard,
    SWEBench, LiveCodeBench.
    """
    return [LMArenaAdapter()]


# ────────────────────────── Pipeline ──────────────────────────


async def run_pipeline() -> Dataset:
    """Run anchor + enrichment phases sequentially, then merge."""
    log = logger.bind(stage="pipeline")
    anchors = _anchor_adapters()
    enrichments = _enrichment_adapters()
    log.info(
        "pipeline.start",
        anchor_count=len(anchors),
        enrichment_count=len(enrichments),
        mode=config.pipeline_mode,
    )

    # ── Phase 1: anchors (parallel) ──
    anchor_results = await asyncio.gather(
        *(a.run() for a in anchors),
        return_exceptions=False,
    )
    anchor_models: list[Model] = []
    source_metas: list[SourceMeta] = []
    for models, meta in anchor_results:
        anchor_models.extend(models)
        source_metas.append(meta)

    anchor_models = _dedupe_by_id(anchor_models)
    log.info("pipeline.anchors.done", anchor_count=len(anchor_models))

    # ── Phase 2: enrichments (parallel) ──
    enrich_results = await asyncio.gather(
        *(a.run() for a in enrichments),
        return_exceptions=False,
    )
    enrichments_by_source: dict[str, list[EnrichmentRecord]] = {}
    enrichment_meta_inputs: list[tuple[str, str, int, str | None]] = []
    for adapter, (records, fetched_at, err) in zip(enrichments, enrich_results):
        enrichments_by_source[adapter.SOURCE_NAME] = records
        enrichment_meta_inputs.append(
            (adapter.SOURCE_NAME, fetched_at, len(records), err)
        )

    # ── Phase 3: merge ──
    merged_models, merge_report = merge_enrichments(
        anchor_models, enrichments_by_source
    )
    log.info(
        "pipeline.merge.done",
        anchor=len(anchor_models),
        merged=len(merged_models),
    )

    # Build SourceMeta for each enrichment source from the merge report
    for source_name, fetched_at, total, err in enrichment_meta_inputs:
        source_metas.append(
            build_enrichment_source_meta(
                source_name,
                fetched_at,
                total,
                merge_report,
                error=err,
            )
        )

    dataset = Dataset.new(models=merged_models, sources=source_metas)
    log.info(
        "pipeline.done",
        models=len(merged_models),
        sources_ok=sum(1 for s in source_metas if s.status == "ok"),
        sources_partial=sum(1 for s in source_metas if s.status == "partial"),
        sources_failed=sum(1 for s in source_metas if s.status == "failed"),
    )
    return dataset


def _dedupe_by_id(models: list[Model]) -> list[Model]:
    """First-write-wins dedup. Anchor universe is currently single-source so
    this is just a safety net for future multi-anchor scenarios."""
    seen: dict[str, Model] = {}
    for m in models:
        if m.id not in seen:
            seen[m.id] = m
    return list(seen.values())


# ────────────────────────── Output ──────────────────────────


def write_dataset(dataset: Dataset, *, pretty: bool = False) -> None:
    """Serialize the dataset to JSON and write to disk."""
    out_path = config.dataset_output_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = dataset.model_dump(mode="json")

    if pretty:
        text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)
    else:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=False)

    out_path.write_text(text + "\n", encoding="utf-8")
    logger.info(
        "dataset.written",
        path=str(out_path),
        size_kb=round(len(text) / 1024, 1),
        models=len(dataset.models),
    )


# ────────────────────────── Entry point ──────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build LLM_Race dataset.json from all sources.",
        prog="python -m src.build",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the output JSON (larger file).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch & build the dataset but don't write to disk.",
    )
    return parser


async def _async_main(args: argparse.Namespace) -> int:
    started = datetime.now(timezone.utc)
    dataset = await run_pipeline()

    if args.dry_run:
        logger.info(
            "dataset.dry_run",
            models=len(dataset.models),
            duration_seconds=(datetime.now(timezone.utc) - started).total_seconds(),
        )
        print(
            f"[dry-run] Would write {len(dataset.models)} models to "
            f"{config.dataset_output_path}",
            file=sys.stderr,
        )
        return 0

    write_dataset(dataset, pretty=args.pretty)
    duration = (datetime.now(timezone.utc) - started).total_seconds()
    logger.info("pipeline.complete", duration_seconds=round(duration, 2))
    return 0


def main() -> int:
    """Sync entry point (for the `llm-race-build` console script)."""
    _setup_logging()
    args = _build_arg_parser().parse_args()
    try:
        return asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        logger.warning("pipeline.interrupted")
        return 130
    except Exception:  # noqa: BLE001
        logger.exception("pipeline.fatal")
        return 1


if __name__ == "__main__":
    sys.exit(main())
