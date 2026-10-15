"""Pydantic data models corresponding to DESIGN.md §3.

These are the canonical in-memory representations. The final dataset.json
is just a serialization of `Dataset`.

All fields are forgiving: a missing data source produces `None` or `[]` rather
than failing the entire pipeline. The `meta.auto_flags` and `data_freshness`
fields carry the audit trail.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ────────────────────────── Component models ──────────────────────────


class Price(BaseModel):
    """All prices normalized to USD per 1M tokens."""

    model_config = ConfigDict(extra="forbid")

    input: float = Field(..., description="Input tokens, USD / 1M tokens")
    output: float = Field(..., description="Output tokens, USD / 1M tokens")
    cache_read: float | None = None
    cache_write: float | None = None
    image_per_unit: float | None = Field(
        None, description="USD per image (if multimodal)"
    )
    request_flat: float | None = Field(
        None, description="USD per request (flat fee, rare)"
    )


class Speed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tokens_per_sec_median: float | None = None
    ttft_ms_p50: float | None = None
    source: str | None = None
    last_updated: str | None = None


class IntelligenceIndex(BaseModel):
    """Composite intelligence score from a single aggregator (e.g. Artificial Analysis)."""

    model_config = ConfigDict(extra="forbid")

    score: float | None = None
    source: str = "artificial_analysis"
    last_updated: str | None = None


class BenchRef(BaseModel):
    """A single benchmark score with provenance."""

    model_config = ConfigDict(extra="forbid")

    name: str
    raw_score: float
    source_url: str
    date: str


class Benchmarks(BaseModel):
    """Categorized benchmark scores. Each category holds zero or more BenchRefs."""

    model_config = ConfigDict(extra="forbid")

    coding: list[BenchRef] = Field(default_factory=list)
    reasoning: list[BenchRef] = Field(default_factory=list)
    knowledge: list[BenchRef] = Field(default_factory=list)
    instruction_following: list[BenchRef] = Field(default_factory=list)
    multilingual_zh: list[BenchRef] = Field(default_factory=list)
    multimodal_vision: list[BenchRef] = Field(default_factory=list)
    long_context: list[BenchRef] = Field(default_factory=list)
    tool_use: list[BenchRef] = Field(default_factory=list)
    safety: list[BenchRef] = Field(default_factory=list)


class HumanPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arena_elo: float | None = None
    arena_rank: int | None = None
    source: str = "lmarena"
    last_updated: str | None = None


class HallucinationRate(BaseModel):
    """Lower is better."""

    model_config = ConfigDict(extra="forbid")

    score: float | None = None
    source: str = "vectara_hhem"
    last_updated: str | None = None


class Meta(BaseModel):
    """Reserved audit / quality signals; automated detection is planned."""

    model_config = ConfigDict(extra="forbid")

    benchmark_saturated: list[str] = Field(default_factory=list)
    contamination_warning: list[str] = Field(default_factory=list)
    auto_flags: list[str] = Field(default_factory=list)


class DataFreshness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_pipeline_run: str
    has_stale_fields: bool = False


class Availability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    openrouter: bool = False
    api_direct: bool = False
    regions: list[str] = Field(default_factory=list)
    rate_limit_notes: str | None = None


Modality = Literal["text", "image", "audio", "video", "pdf"]


# ────────────────────────── Main model ──────────────────────────


class Model(BaseModel):
    """The canonical model record (DESIGN.md §3)."""

    model_config = ConfigDict(extra="forbid")

    # ── Identity ──
    id: str = Field(
        ...,
        description="Canonical ID, prefers OpenRouter slug (e.g. 'anthropic/claude-opus-4.7')",
    )
    name: str
    vendor: str
    family: str | None = None
    version: str | None = None
    release_date: str | None = None
    is_open_weight: bool = False
    license: str | None = None

    # ── Auto-tiering (set by merger.py based on source_coverage) ──
    tier: Literal[1, 2, 3] = 3
    source_coverage: list[str] = Field(default_factory=list)

    # ── Modality & context ──
    modalities_in: list[Modality] = Field(default_factory=lambda: ["text"])
    modalities_out: list[Modality] = Field(default_factory=lambda: ["text"])
    context_window: int = 0
    context_effective: int | None = None

    # ── Pricing & performance ──
    price: Price
    speed: Speed = Field(default_factory=Speed)

    # ── Capabilities ──
    intelligence_index: IntelligenceIndex = Field(default_factory=IntelligenceIndex)
    benchmarks: Benchmarks = Field(default_factory=Benchmarks)
    human_preference: HumanPreference = Field(default_factory=HumanPreference)
    hallucination_rate: HallucinationRate = Field(default_factory=HallucinationRate)

    # ── Usage / availability ──
    usage_rank: int | None = Field(
        None, description="Rank in OpenRouter total call volume (lower = more popular)"
    )
    availability: Availability = Field(default_factory=Availability)

    # ── Audit ──
    meta: Meta = Field(default_factory=Meta)
    data_freshness: DataFreshness


# ────────────────────────── Top-level dataset ──────────────────────────


class SourceMeta(BaseModel):
    """Metadata about each source's last successful fetch."""

    model_config = ConfigDict(extra="forbid")

    name: str
    last_fetched_at: str
    model_count: int
    status: Literal["ok", "partial", "failed"] = "ok"
    error: str | None = None


class Dataset(BaseModel):
    """The top-level dataset.json schema."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    generated_at: str
    models: list[Model]
    sources: list[SourceMeta]

    @classmethod
    def new(cls, models: list[Model], sources: list[SourceMeta]) -> "Dataset":
        return cls(
            generated_at=datetime.now(timezone.utc).isoformat(),
            models=models,
            sources=sources,
        )
