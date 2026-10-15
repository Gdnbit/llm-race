"""Vendor-scoped fuzzy match against the anchor universe (OpenRouter IDs).

Uses Python's stdlib `difflib.SequenceMatcher` to avoid a heavy dependency
on `rapidfuzz`. Performance is fine for our scale (~350 anchor IDs × ~270
LMArena rows = ~95k comparisons).
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from .normalize import strip_date_suffix


# Match-score threshold: stems must be >= this similar to count as a match.
DEFAULT_MIN_RATIO = 0.85


@dataclass(frozen=True)
class FuzzyHit:
    canonical_id: str
    score: float


def fuzzy_match(
    candidate_id: str,
    anchor_ids: list[str],
    *,
    min_ratio: float = DEFAULT_MIN_RATIO,
) -> FuzzyHit | None:
    """Find the best match for `candidate_id` in `anchor_ids`.

    Matching is **vendor-scoped**: only anchor IDs sharing the same vendor
    prefix as the candidate are considered. This avoids false positives like
    matching "google/gemini-2.5-pro" against "anthropic/claude-2.5-sonnet".

    Returns None if no anchor in the same vendor scores >= min_ratio.

    >>> hit = fuzzy_match("google/gemini-2.5-pro-preview", ["google/gemini-2.5-pro", "openai/gpt-4"])
    >>> hit is not None and hit.canonical_id == "google/gemini-2.5-pro"
    True
    """
    if not candidate_id or "/" not in candidate_id:
        return None

    vendor, _, _ = candidate_id.partition("/")
    in_vendor = [a for a in anchor_ids if a.startswith(f"{vendor}/")]
    if not in_vendor:
        return None

    # First try exact match on the full ID
    if candidate_id in in_vendor:
        return FuzzyHit(canonical_id=candidate_id, score=1.0)

    # Then try matching against date-stripped variants of both
    cand_stripped = strip_date_suffix(candidate_id)
    if cand_stripped != candidate_id and cand_stripped in in_vendor:
        return FuzzyHit(canonical_id=cand_stripped, score=0.99)

    # Finally fall back to similarity ratio
    best: FuzzyHit | None = None
    cand_stem = candidate_id.split("/", 1)[1]
    for anchor in in_vendor:
        anchor_stem = anchor.split("/", 1)[1]

        # Score against both raw and date-stripped versions
        ratio = SequenceMatcher(None, cand_stem, anchor_stem).ratio()
        if ratio < min_ratio:
            continue
        if best is None or ratio > best.score:
            best = FuzzyHit(canonical_id=anchor, score=ratio)

    return best
