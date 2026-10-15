"""Manual alias registry — highest-precedence override layer.

Aliases are loaded from `src/data/alias_lmarena.yaml`. A `null` value
indicates an intentional skip (model known not to exist in the anchor
universe), distinct from "no entry" (caller should fall through to other
strategies).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml


_DATA_DIR = Path(__file__).parent.parent / "data"
_ALIAS_PATH = _DATA_DIR / "alias_lmarena.yaml"


@dataclass(frozen=True)
class AliasEntry:
    raw_key: str
    canonical_id: str | None  # None = explicit skip


@dataclass
class AliasRegistry:
    """Registry of manual `raw_key → canonical_id | skip` mappings."""

    entries: dict[str, AliasEntry] = field(default_factory=dict)

    def lookup(self, raw_key: str) -> AliasEntry | None:
        """Return the entry for `raw_key` if any, else None.

        The distinction:
          - `None` return → no entry, fall through to other strategies
          - `AliasEntry(canonical_id=None)` → explicit skip, do not align
          - `AliasEntry(canonical_id="...")` → use this canonical ID directly
        """
        return self.entries.get(raw_key)

    @property
    def skip_count(self) -> int:
        return sum(1 for e in self.entries.values() if e.canonical_id is None)

    @property
    def alias_count(self) -> int:
        return sum(1 for e in self.entries.values() if e.canonical_id is not None)


@lru_cache(maxsize=1)
def load_alias_registry() -> AliasRegistry:
    """Load aliases from disk (cached).

    Schema (YAML):
        aliases:
          "Some LMArena Model Name": canonical/id        # explicit alias
          "Research Only Model": null                     # explicit skip
    """
    if not _ALIAS_PATH.exists():
        return AliasRegistry()

    with _ALIAS_PATH.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    entries: dict[str, AliasEntry] = {}
    for k, v in (raw.get("aliases") or {}).items():
        key = str(k)
        if v is None:
            entries[key] = AliasEntry(raw_key=key, canonical_id=None)
        elif isinstance(v, str) and v.strip():
            entries[key] = AliasEntry(raw_key=key, canonical_id=v.strip())
        # else: malformed entry, silently ignore

    return AliasRegistry(entries=entries)
