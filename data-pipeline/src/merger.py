"""Cross-source merge.

The pipeline has two kinds of sources:
  * **Anchor source** (OpenRouter): produces full `Model` records with
    canonical IDs of the form `vendor/model`.
  * **Enrichment sources** (LMArena, Vectara HHEM, Artificial Analysis, …):
    contribute partial signals (Elo rating, hallucination rate, intelligence
    score, etc.) keyed by their own naming conventions.

This module:
  1. Aligns each enrichment record's `raw_key` to a canonical anchor ID,
  2. Merges the partial signals into the corresponding anchor `Model`,
  3. Updates `source_coverage` and recomputes `tier` to reflect coverage.

Tier rule (per DESIGN.md §4.2):
    - tier=1 if covered by ≥4 sources
    - tier=2 if covered by 2-3 sources
    - tier=3 if covered by 1 source (anchor only)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from .alignment import Aligner, AlignmentResult, AlignmentStrategy
from .models import (
    Benchmarks,
    HallucinationRate,
    HumanPreference,
    IntelligenceIndex,
    Model,
    SourceMeta,
)

logger = structlog.get_logger(__name__)


# ────────────────────────── Enrichment payload ──────────────────────────


@dataclass
class EnrichmentRecord:
    """A partial-signal contribution from a non-anchor source.

    The `raw_key` and `organization` fields drive ID alignment. Any of the
    `*_partial` fields may be set by the producing adapter; merger applies
    only the non-None ones.
    """

    raw_key: str
    organization: str
    source: str  # e.g. "lmarena"

    # Optional partial signals (each one is fully-formed when present)
    human_preference: HumanPreference | None = None
    intelligence_index: IntelligenceIndex | None = None
    hallucination_rate: HallucinationRate | None = None
    benchmarks_patch: dict[str, Any] = field(default_factory=dict)


# ────────────────────────── Merge core ──────────────────────────


@dataclass
class MergeReport:
    """Diagnostic counts surfaced after `merge_enrichments`."""

    by_source: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, source: str, strategy: AlignmentStrategy) -> None:
        bucket = self.by_source.setdefault(source, {})
        bucket[strategy.value] = bucket.get(strategy.value, 0) + 1

    def total_matched(self, source: str) -> int:
        bucket = self.by_source.get(source, {})
        return sum(
            v
            for k, v in bucket.items()
            if k
            not in {AlignmentStrategy.NO_MATCH.value, AlignmentStrategy.ALIAS_SKIP.value}
        )

    def total(self, source: str) -> int:
        return sum(self.by_source.get(source, {}).values())


def merge_enrichments(
    anchor_models: list[Model],
    enrichments_by_source: dict[str, list[EnrichmentRecord]],
) -> tuple[list[Model], MergeReport]:
    """Apply enrichment records to anchor models, returning new model list.

    `anchor_models` is mutated in-place (fields replaced) and also returned
    as a fresh list. The original Model objects are NOT shared across runs
    of the pipeline (they're constructed each time), so in-place mutation
    is safe.
    """
    log = logger.bind(stage="merge")
    by_id: dict[str, Model] = {m.id: m for m in anchor_models}
    aligner = Aligner(anchor_ids=set(by_id.keys()))
    report = MergeReport()

    for source_name, records in enrichments_by_source.items():
        for rec in records:
            result = aligner.align(rec.raw_key, rec.organization)
            report.record(source_name, result.strategy)

            if result.canonical_id is None:
                if result.strategy is AlignmentStrategy.NO_MATCH:
                    log.warning(
                        "merge.unmatched",
                        source=source_name,
                        raw_key=rec.raw_key,
                        organization=rec.organization,
                    )
                continue  # skip silently for ALIAS_SKIP

            target = by_id.get(result.canonical_id)
            if target is None:
                # Aligner returned an ID we don't actually have (alias points
                # to a model not in current OpenRouter catalog). Log + skip.
                log.warning(
                    "merge.target_missing",
                    source=source_name,
                    raw_key=rec.raw_key,
                    aligned_to=result.canonical_id,
                )
                continue

            _apply_enrichment(target, rec, source_name)

        log.info(
            "merge.source.summary",
            source=source_name,
            total=report.total(source_name),
            matched=report.total_matched(source_name),
        )

    # Update tiers based on final source_coverage
    for m in by_id.values():
        m.tier = _compute_tier(len(m.source_coverage))

    return list(by_id.values()), report


def _apply_enrichment(target: Model, rec: EnrichmentRecord, source: str) -> None:
    """Mutate `target` to reflect the partial signals in `rec`."""
    if rec.human_preference is not None:
        target.human_preference = rec.human_preference

    if rec.intelligence_index is not None:
        target.intelligence_index = rec.intelligence_index

    if rec.hallucination_rate is not None:
        target.hallucination_rate = rec.hallucination_rate

    if rec.benchmarks_patch:
        # benchmarks is a categorized dict[str, list[BenchRef]]; merge each
        # category by extending lists.
        existing = target.benchmarks.model_dump()
        for category, refs in rec.benchmarks_patch.items():
            if not isinstance(refs, list):
                continue
            existing.setdefault(category, [])
            existing[category].extend(refs)
        target.benchmarks = Benchmarks(**existing)

    if source not in target.source_coverage:
        target.source_coverage = [*target.source_coverage, source]


def _compute_tier(coverage_count: int) -> int:
    """DESIGN.md §4.2 — automatic tier from coverage count."""
    if coverage_count >= 4:
        return 1
    if coverage_count >= 2:
        return 2
    return 3


# ────────────────────────── Source meta helpers ──────────────────────────


def build_enrichment_source_meta(
    source_name: str,
    fetched_at: str,
    record_count: int,
    report: MergeReport,
    *,
    error: str | None = None,
) -> SourceMeta:
    """Build a SourceMeta from a merge report for an enrichment source."""
    if error:
        return SourceMeta(
            name=source_name,
            last_fetched_at=fetched_at,
            model_count=0,
            status="failed",
            error=error,
        )

    matched = report.total_matched(source_name)
    total = report.total(source_name)
    status = "ok" if matched == total else "partial" if matched > 0 else "failed"

    return SourceMeta(
        name=source_name,
        last_fetched_at=fetched_at,
        model_count=matched,
        status=status,
        error=None
        if matched == total
        else f"{total - matched}/{total} records unmatched",
    )
