"""Base classes for data source adapters.

Two adapter kinds:
  * `SourceAdapter` — anchor sources that produce full `Model` records with
    canonical IDs (currently only OpenRouter).
  * `EnrichmentAdapter` — non-anchor sources that produce `EnrichmentRecord`
    objects with source-specific identifiers, to be aligned and merged
    against the anchor universe in `merger.py`.

Design contract (both kinds):
- Per-record errors are logged and skipped, never raised.
- Catastrophic failures (source unreachable) propagate; the orchestrator
  catches them and records failure metadata while leaving other sources intact.
- Each adapter exposes `SOURCE_NAME` used in coverage and source metadata.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import config
from ..models import Model, SourceMeta

if TYPE_CHECKING:
    from ..merger import EnrichmentRecord

logger = structlog.get_logger(__name__)


class SourceAdapter(ABC):
    """Anchor source adapter — produces full `Model` records."""

    SOURCE_NAME: str

    def __init__(self) -> None:
        if not hasattr(self, "SOURCE_NAME"):
            raise NotImplementedError(
                f"{self.__class__.__name__} must define SOURCE_NAME"
            )

    @abstractmethod
    async def fetch(self) -> list[Model]:
        """Fetch source data and return Model records."""

    async def run(self) -> tuple[list[Model], SourceMeta]:
        """Top-level run with error capture and metadata generation."""
        log = logger.bind(source=self.SOURCE_NAME)
        started_at = datetime.now(timezone.utc).isoformat()

        try:
            log.info("source.fetch.start")
            models = await self.fetch()
            log.info("source.fetch.ok", count=len(models))
            return models, SourceMeta(
                name=self.SOURCE_NAME,
                last_fetched_at=started_at,
                model_count=len(models),
                status="ok",
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("source.fetch.failed", error=str(exc))
            return [], SourceMeta(
                name=self.SOURCE_NAME,
                last_fetched_at=started_at,
                model_count=0,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )


class EnrichmentAdapter(ABC):
    """Enrichment source adapter — produces partial-signal records."""

    SOURCE_NAME: str

    def __init__(self) -> None:
        if not hasattr(self, "SOURCE_NAME"):
            raise NotImplementedError(
                f"{self.__class__.__name__} must define SOURCE_NAME"
            )

    @abstractmethod
    async def fetch(self) -> list["EnrichmentRecord"]:
        """Fetch source data and return EnrichmentRecord objects."""

    async def run(self) -> tuple[list["EnrichmentRecord"], str, str | None]:
        """Return `(records, fetched_at, error)` for downstream merging."""
        log = logger.bind(source=self.SOURCE_NAME)
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            log.info("enrichment.fetch.start")
            records = await self.fetch()
            log.info("enrichment.fetch.ok", count=len(records))
            return records, fetched_at, None
        except Exception as exc:  # noqa: BLE001
            log.exception("enrichment.fetch.failed", error=str(exc))
            return [], fetched_at, f"{type(exc).__name__}: {exc}"


async def http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """GET a JSON endpoint with retries and exponential backoff."""
    log = logger.bind(url=url)
    actual_timeout = timeout or config.http_timeout_seconds

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(config.http_max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
        reraise=True,
    ):
        with attempt:
            attempt_num = attempt.retry_state.attempt_number
            if attempt_num > 1:
                log.info("http.retry", attempt=attempt_num)

            async with httpx.AsyncClient(timeout=actual_timeout) as client:
                resp = await client.get(url, headers=headers or {}, params=params)
                resp.raise_for_status()
                return resp.json()

    raise RuntimeError("unreachable")
