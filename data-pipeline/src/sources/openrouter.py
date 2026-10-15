"""OpenRouter adapter.

Fetches the public model catalog from https://openrouter.ai/api/v1/models.
This endpoint is currently public (no API key required) and is the most
authoritative source for:
  - canonical model IDs (used as our `Model.id`)
  - pricing (in USD per token — we convert to USD per 1M tokens)
  - context window
  - input/output modalities
  - vendor identification

Other dimensions (intelligence, benchmarks, hallucination, etc.) come from
future adapters and are merged in `merger.py`.

Run standalone for debugging:
    python -m src.sources.openrouter
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Any

import structlog

from ..config import config
from ..models import (
    Availability,
    DataFreshness,
    Model,
    Modality,
    Price,
)
from .base import SourceAdapter, http_get_json

logger = structlog.get_logger(__name__)


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/models"

# OpenRouter modality strings → our normalized Modality literals
_MODALITY_MAP: dict[str, Modality] = {
    "text": "text",
    "image": "image",
    "audio": "audio",
    "video": "video",
    "file": "pdf",  # OpenRouter uses "file" for PDF inputs
}


class OpenRouterAdapter(SourceAdapter):
    SOURCE_NAME = "openrouter"

    async def fetch(self) -> list[Model]:
        log = logger.bind(source=self.SOURCE_NAME)
        headers: dict[str, str] = {}
        if config.openrouter_api_key:
            headers["Authorization"] = f"Bearer {config.openrouter_api_key}"

        data = await http_get_json(OPENROUTER_API_URL, headers=headers)
        raw_models = data.get("data", [])
        log.info("openrouter.fetched", count=len(raw_models))

        models: list[Model] = []
        skipped: list[tuple[str, str]] = []

        for raw in raw_models:
            try:
                model = self._parse_one(raw)
                if model is not None:
                    models.append(model)
            except Exception as exc:  # noqa: BLE001 — per-record tolerance
                model_id = raw.get("id", "<unknown>")
                skipped.append((model_id, f"{type(exc).__name__}: {exc}"))
                log.warning(
                    "openrouter.parse.skip",
                    model_id=model_id,
                    error=str(exc),
                )

        if skipped:
            log.info("openrouter.parse.summary", parsed=len(models), skipped=len(skipped))

        return models

    # ────────────────────── Single-record parsing ──────────────────────

    def _parse_one(self, raw: dict[str, Any]) -> Model | None:
        model_id = raw.get("id")
        if not model_id or "/" not in model_id:
            # OpenRouter IDs are always of the form "vendor/model"
            return None

        vendor, _, _ = model_id.partition("/")

        # ── Pricing ──
        # OpenRouter returns USD per token (string). We convert to USD per 1M.
        pricing_raw = raw.get("pricing") or {}
        try:
            input_per_token = float(pricing_raw.get("prompt", "0") or "0")
            output_per_token = float(pricing_raw.get("completion", "0") or "0")
        except (TypeError, ValueError):
            input_per_token = output_per_token = 0.0

        price = Price(
            input=input_per_token * 1_000_000,
            output=output_per_token * 1_000_000,
            image_per_unit=_safe_float(pricing_raw.get("image")),
            request_flat=_safe_float(pricing_raw.get("request")),
        )

        # ── Context window ──
        context_window = (
            raw.get("context_length")
            or (raw.get("top_provider") or {}).get("context_length")
            or 0
        )

        # ── Modalities ──
        arch = raw.get("architecture") or {}
        modalities_in = _normalize_modalities(arch.get("input_modalities"))
        modalities_out = _normalize_modalities(arch.get("output_modalities"))

        # Fall back to parsing "modality" string ("text+image->text")
        if not modalities_in or not modalities_out:
            modality_str = arch.get("modality") or "text->text"
            mi, mo = _parse_modality_string(modality_str)
            modalities_in = modalities_in or mi
            modalities_out = modalities_out or mo

        # ── Release date ──
        release_date: str | None = None
        created_ts = raw.get("created")
        if isinstance(created_ts, (int, float)) and created_ts > 0:
            release_date = datetime.fromtimestamp(
                created_ts, tz=timezone.utc
            ).date().isoformat()

        # ── Build the Model ──
        return Model(
            id=model_id,
            name=raw.get("name") or model_id,
            vendor=vendor,
            release_date=release_date,
            modalities_in=modalities_in,
            modalities_out=modalities_out,
            context_window=int(context_window),
            price=price,
            source_coverage=[self.SOURCE_NAME],
            availability=Availability(openrouter=True),
            data_freshness=DataFreshness(
                last_pipeline_run=datetime.now(timezone.utc).isoformat(),
                has_stale_fields=False,
            ),
        )


# ────────────────────────── Helpers ──────────────────────────


def _safe_float(value: Any) -> float | None:
    """Convert OpenRouter's stringified floats safely; '0' becomes None."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _normalize_modalities(values: Any) -> list[Modality]:
    """Convert OpenRouter modality strings to our Modality literal."""
    if not isinstance(values, list):
        return []
    out: list[Modality] = []
    for v in values:
        if not isinstance(v, str):
            continue
        mapped = _MODALITY_MAP.get(v.lower())
        if mapped and mapped not in out:
            out.append(mapped)
    return out


def _parse_modality_string(modality_str: str) -> tuple[list[Modality], list[Modality]]:
    """Parse strings like 'text+image->text' into ([text, image], [text])."""
    if "->" not in modality_str:
        return ["text"], ["text"]
    left, right = modality_str.split("->", 1)

    def _split(s: str) -> list[Modality]:
        parts = [p.strip().lower() for p in s.split("+") if p.strip()]
        out: list[Modality] = []
        for p in parts:
            mapped = _MODALITY_MAP.get(p)
            if mapped and mapped not in out:
                out.append(mapped)
        return out or ["text"]

    return _split(left), _split(right)


# ────────────────────────── Standalone run for debugging ──────────────────────────


async def _main() -> None:
    """Print first few parsed records for quick inspection."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(
                colors=False, exception_formatter=structlog.dev.plain_traceback
            ),
        ],
    )
    adapter = OpenRouterAdapter()
    models, meta = await adapter.run()

    print(f"\n=== OpenRouter fetch summary ===")
    print(f"Status: {meta.status}")
    print(f"Models fetched: {len(models)}")
    if meta.error:
        print(f"Error: {meta.error}")
        sys.exit(1)

    print(f"\n=== Sample (first 3 records) ===")
    for m in models[:3]:
        print(json.dumps(m.model_dump(), indent=2, ensure_ascii=False))
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(_main())
