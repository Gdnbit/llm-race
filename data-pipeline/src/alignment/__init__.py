"""Cross-source ID alignment.

Anchor source (OpenRouter) provides canonical IDs in the form `vendor/model`.
Enrichment sources (LMArena, Vectara HHEM, etc.) use their own naming schemes
and must be aligned to the canonical ID before merging.

The aligner uses a layered strategy:
    1. Manual alias lookup (highest precedence; handles edge cases)
    2. Vendor-mapped exact ID match
    3. Vendor-scoped fuzzy match against anchor IDs
    4. Log warning + return None (caller decides whether to drop record)

See `aligner.py::Aligner` for the public API.
"""

from .aligner import Aligner, AlignmentResult, AlignmentStrategy

__all__ = ["Aligner", "AlignmentResult", "AlignmentStrategy"]
