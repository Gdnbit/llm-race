"""Model name / vendor normalization helpers.

Used to convert source-specific identifiers (e.g. LMArena's
"Gemini-2.5-Pro" + organization "Google") into a candidate canonical ID
(e.g. "google/gemini-2.5-pro") that can be tested against the anchor
universe (OpenRouter IDs).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

# ────────────────────────── Vendor mapping ──────────────────────────


_DATA_DIR = Path(__file__).parent.parent / "data"
_VENDOR_MAP_PATH = _DATA_DIR / "vendor_map.yaml"


@lru_cache(maxsize=1)
def _load_vendor_map() -> dict[str, str]:
    """Load the LMArena org → canonical vendor mapping (cached)."""
    if not _VENDOR_MAP_PATH.exists():
        return {}
    with _VENDOR_MAP_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def map_vendor(org: str) -> str:
    """Map a source `organization` string to canonical vendor prefix.

    Falls back to a sanitized lowercase form of the org if no explicit mapping
    exists. Sanitization: lowercase, alphanumeric + hyphen only.

    >>> map_vendor("Google")
    'google'
    >>> map_vendor("Mistral AI")
    'mistralai'
    >>> map_vendor("UnknownVendor X")
    'unknownvendor-x'
    """
    if not org:
        return ""
    explicit = _load_vendor_map().get(org.strip())
    if explicit:
        return explicit

    # Fallback: lowercase, replace whitespace with hyphen, strip non-alnum
    sanitized = re.sub(r"[^a-z0-9 \-]", "", org.lower())
    sanitized = re.sub(r"\s+", "-", sanitized.strip())
    return sanitized


# ────────────────────────── Model name normalization ──────────────────────────


_PAREN_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")
_DATE_SUFFIX = re.compile(r"-\d{4}-?\d{2}-?\d{2}$")  # -YYYY-MM-DD or -YYYYMMDD


def normalize_model_name(name: str) -> str:
    """Lower-case + strip parenthesized suffixes + collapse separators.

    LMArena models often have a parenthesized version date like
    "ChatGPT-4o-latest (2025-03-26)" or experimental tags like
    "Llama-4-Maverick-03-26-Experimental". We normalize the surface form
    to make exact-match lookup more likely.

    >>> normalize_model_name("Gemini-2.5-Pro")
    'gemini-2.5-pro'
    >>> normalize_model_name("ChatGPT-4o-latest (2025-03-26)")
    'chatgpt-4o-latest'
    >>> normalize_model_name("Qwen3-235B-A22B-Instruct-2507")
    'qwen3-235b-a22b-instruct-2507'
    """
    if not name:
        return ""

    # Strip trailing "(date)" or "(comment)"
    out = _PAREN_SUFFIX.sub("", name).strip()

    # Lowercase
    out = out.lower()

    # Collapse runs of separators
    out = re.sub(r"[\s_]+", "-", out)
    out = re.sub(r"-+", "-", out).strip("-")

    return out


def candidate_canonical_id(org: str, model_name: str) -> str:
    """Produce a `vendor/model` candidate ID from source fields.

    >>> candidate_canonical_id("Google", "Gemini-2.5-Pro")
    'google/gemini-2.5-pro'
    >>> candidate_canonical_id("Alibaba", "Qwen3-235B-A22B-Instruct-2507")
    'qwen/qwen3-235b-a22b-instruct-2507'
    """
    vendor = map_vendor(org)
    name = normalize_model_name(model_name)
    if not vendor or not name:
        return ""
    return f"{vendor}/{name}"


def strip_date_suffix(model_id: str) -> str:
    """Remove a trailing -YYYY-MM-DD or -YYYYMMDD suffix from a model ID stem.

    Used to soften fuzzy matching, since LMArena often pins a date but the
    OpenRouter slug may use the un-dated alias.
    """
    if "/" not in model_id:
        return model_id
    vendor, _, stem = model_id.partition("/")
    return f"{vendor}/{_DATE_SUFFIX.sub('', stem)}"
