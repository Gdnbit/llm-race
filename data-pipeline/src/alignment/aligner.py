"""Top-level aligner combining alias / exact / fuzzy strategies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

import structlog

from .alias import load_alias_registry
from .fuzzy import DEFAULT_MIN_RATIO, fuzzy_match
from .normalize import candidate_canonical_id

logger = structlog.get_logger(__name__)


class AlignmentStrategy(str, Enum):
    """How a `raw_key` was resolved to a canonical ID (or not)."""

    ALIAS_EXACT = "alias_exact"
    ALIAS_SKIP = "alias_skip"
    EXACT_MATCH = "exact_match"
    FUZZY = "fuzzy"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class AlignmentResult:
    raw_key: str  # source-side identifier, e.g. LMArena's `model` value
    canonical_id: str | None
    strategy: AlignmentStrategy
    score: float | None = None  # populated for FUZZY


class Aligner:
    """Aligns source-specific identifiers to canonical anchor IDs.

    Construction:
        aligner = Aligner(anchor_ids={m.id for m in openrouter_models})

    Usage:
        result = aligner.align(raw_key="Gemini-2.5-Pro", organization="Google")
        if result.canonical_id:
            # use result.canonical_id as the merge key
            ...
    """

    def __init__(
        self,
        anchor_ids: set[str] | list[str],
        *,
        fuzzy_min_ratio: float = DEFAULT_MIN_RATIO,
    ) -> None:
        self._anchor_set: set[str] = set(anchor_ids)
        self._anchor_list: list[str] = sorted(self._anchor_set)
        self._fuzzy_min_ratio = fuzzy_min_ratio
        self._aliases = load_alias_registry()
        self._log = logger.bind(component="aligner")

    def align(
        self,
        raw_key: str,
        organization: str,
    ) -> AlignmentResult:
        """Resolve a source-side identifier to a canonical anchor ID."""
        # Layer 1: manual alias
        alias_entry = self._aliases.lookup(raw_key)
        if alias_entry is not None:
            if alias_entry.canonical_id is None:
                return AlignmentResult(
                    raw_key=raw_key,
                    canonical_id=None,
                    strategy=AlignmentStrategy.ALIAS_SKIP,
                )
            return AlignmentResult(
                raw_key=raw_key,
                canonical_id=alias_entry.canonical_id,
                strategy=AlignmentStrategy.ALIAS_EXACT,
            )

        # Layer 2 & 3: vendor-mapped exact + fuzzy
        candidate = candidate_canonical_id(organization, raw_key)
        if not candidate:
            return AlignmentResult(
                raw_key=raw_key,
                canonical_id=None,
                strategy=AlignmentStrategy.NO_MATCH,
            )

        if candidate in self._anchor_set:
            return AlignmentResult(
                raw_key=raw_key,
                canonical_id=candidate,
                strategy=AlignmentStrategy.EXACT_MATCH,
            )

        hit = fuzzy_match(
            candidate,
            self._anchor_list,
            min_ratio=self._fuzzy_min_ratio,
        )
        if hit is not None:
            return AlignmentResult(
                raw_key=raw_key,
                canonical_id=hit.canonical_id,
                strategy=AlignmentStrategy.FUZZY,
                score=hit.score,
            )

        return AlignmentResult(
            raw_key=raw_key,
            canonical_id=None,
            strategy=AlignmentStrategy.NO_MATCH,
        )

    def report(
        self,
        results: list[AlignmentResult],
        *,
        source_name: str,
    ) -> None:
        """Log a summary of alignment outcomes for a source."""
        counts: dict[str, int] = {}
        for r in results:
            counts[r.strategy.value] = counts.get(r.strategy.value, 0) + 1
        matched = sum(
            v
            for k, v in counts.items()
            if k not in {AlignmentStrategy.ALIAS_SKIP.value, AlignmentStrategy.NO_MATCH.value}
        )
        self._log.info(
            "alignment.summary",
            source=source_name,
            total=len(results),
            matched=matched,
            **counts,
        )
        # Surface unmatched entries for human review (helps grow alias_lmarena.yaml)
        unmatched = [r for r in results if r.strategy is AlignmentStrategy.NO_MATCH]
        for r in unmatched:
            self._log.warning(
                "alignment.unmatched",
                source=source_name,
                raw_key=r.raw_key,
            )
