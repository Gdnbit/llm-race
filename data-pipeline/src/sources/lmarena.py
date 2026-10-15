"""LMArena (Chatbot Arena) adapter.

Fetches the public LMArena leaderboard CSV from the
`fboulnois/llm-leaderboard-csv` GitHub release feed. Returns
`EnrichmentRecord`s carrying the Elo rating; the merger aligns each row
to a canonical OpenRouter ID and writes `human_preference.arena_elo` /
`arena_rank` onto the corresponding `Model`.

Why this source instead of scraping LMArena's HF Space?
  * The HF Space embeds JS/Gradio that's painful to parse server-side.
  * The community-maintained CSVs are stable, versioned, and small.

Tradeoff: the CSV repo updates monthly at best (latest release was 8
months stale at MVP time). We populate `human_preference.last_updated`
with the release tag so downstream tools can flag stale rankings.

Run standalone for debugging:
    python -m src.sources.lmarena
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import sys
from typing import Any

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import config
from ..merger import EnrichmentRecord
from ..models import HumanPreference
from .base import EnrichmentAdapter

logger = structlog.get_logger(__name__)


# Public release feed for LMArena CSVs. Tag and asset names are stable.
RELEASES_API = "https://api.github.com/repos/fboulnois/llm-leaderboard-csv/releases/latest"
TEXT_CSV_NAME = "lmarena_text.csv"


class LMArenaAdapter(EnrichmentAdapter):
    SOURCE_NAME = "lmarena"

    async def fetch(self) -> list[EnrichmentRecord]:
        log = logger.bind(source=self.SOURCE_NAME)

        release = await self._fetch_release_metadata()
        tag = release.get("tag_name") or "unknown"
        published = release.get("published_at") or ""

        text_asset = next(
            (a for a in (release.get("assets") or []) if a.get("name") == TEXT_CSV_NAME),
            None,
        )
        if text_asset is None:
            raise RuntimeError(
                f"release {tag} has no asset named '{TEXT_CSV_NAME}'"
            )

        url = text_asset["browser_download_url"]
        log.info("lmarena.release", tag=tag, published=published, url=url)

        csv_text = await _http_get_text(url)
        log.info("lmarena.csv.fetched", bytes=len(csv_text))

        records = self._parse_csv(csv_text, last_updated=published or tag, log=log)
        log.info("lmarena.parsed", count=len(records))
        return records

    # ────────────────────── HTTP helpers ──────────────────────

    async def _fetch_release_metadata(self) -> dict[str, Any]:
        """Fetch the latest release JSON. Auth-optional (token boosts rate limits)."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "LLM-Race-Pipeline",
        }
        # GitHub allows 60 unauth requests/hour per IP; for cron pipelines we
        # may want to provide a token, but it's optional.
        token = getattr(config, "github_token", None)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(config.http_max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=config.http_timeout_seconds) as client:
                    resp = await client.get(RELEASES_API, headers=headers)
                    resp.raise_for_status()
                    return resp.json()

        raise RuntimeError("unreachable")

    # ────────────────────── CSV parsing ──────────────────────

    def _parse_csv(
        self,
        csv_text: str,
        *,
        last_updated: str,
        log: Any,
    ) -> list[EnrichmentRecord]:
        records: list[EnrichmentRecord] = []
        reader = csv.DictReader(io.StringIO(csv_text))

        for row in reader:
            try:
                record = self._parse_row(row, last_updated=last_updated)
                if record is not None:
                    records.append(record)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "lmarena.parse.skip",
                    raw_row=dict(row),
                    error=f"{type(exc).__name__}: {exc}",
                )
        return records

    def _parse_row(
        self,
        row: dict[str, str],
        *,
        last_updated: str,
    ) -> EnrichmentRecord | None:
        model_name = (row.get("model") or "").strip()
        org = (row.get("organization") or "").strip()
        if not model_name:
            return None

        elo = _safe_float(row.get("arena_score"))
        if elo is None:
            return None

        rank = _safe_int(row.get("rank_stylectrl") or row.get("rank"))

        return EnrichmentRecord(
            raw_key=model_name,
            organization=org,
            source=self.SOURCE_NAME,
            human_preference=HumanPreference(
                arena_elo=elo,
                arena_rank=rank,
                source="lmarena",
                last_updated=last_updated,
            ),
        )


# ────────────────────────── Helpers ──────────────────────────


async def _http_get_text(url: str, *, timeout: float | None = None) -> str:
    """GET a plain-text endpoint with retry. Used for CSV downloads."""
    actual_timeout = timeout or config.http_timeout_seconds

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(config.http_max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
        reraise=True,
    ):
        with attempt:
            async with httpx.AsyncClient(
                timeout=actual_timeout,
                follow_redirects=True,  # GitHub asset URLs redirect to S3
            ) as client:
                resp = await client.get(url, headers={"User-Agent": "LLM-Race-Pipeline"})
                resp.raise_for_status()
                # CSV may not declare encoding; httpx defaults to UTF-8 which is fine
                return resp.text

    raise RuntimeError("unreachable")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ────────────────────────── Standalone debug ──────────────────────────


async def _main() -> None:
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(
                colors=False, exception_formatter=structlog.dev.plain_traceback
            ),
        ],
    )
    adapter = LMArenaAdapter()
    records, fetched_at, err = await adapter.run()
    print("\n=== LMArena fetch summary ===")
    print(f"Fetched at: {fetched_at}")
    print(f"Records   : {len(records)}")
    if err:
        print(f"Error: {err}")
        sys.exit(1)
    print("\n=== Top-5 records ===")
    for r in records[:5]:
        payload = {
            "raw_key": r.raw_key,
            "organization": r.organization,
            "arena_elo": r.human_preference and r.human_preference.arena_elo,
            "arena_rank": r.human_preference and r.human_preference.arena_rank,
        }
        print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(_main())
