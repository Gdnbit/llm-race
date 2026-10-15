"""Configuration loaded from environment variables.

The pipeline keeps credentials out of source control. Values may be injected
through the shell, CI, or any external secret manager. For local development,
a git-ignored `.env` file is supported as a convenience fallback.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv_if_present() -> None:
    """Load a local git-ignored `.env` file when present.

    Existing process environment variables always take precedence so CI and
    external secret managers can inject credentials without being overwritten.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_if_present()


@dataclass(frozen=True)
class Config:
    """Pipeline configuration (immutable, loaded once)."""

    # ───── API keys (all optional at module load time) ─────
    openrouter_api_key: str | None
    """OpenRouter API key. The model catalog is currently public, but a key
    may provide higher rate limits or support future authenticated endpoints."""

    artificial_analysis_api_key: str | None
    """Reserved for the planned Artificial Analysis adapter; currently unused."""

    anthropic_api_key: str | None
    """Reserved for planned AI-assisted alignment; currently unused."""

    huggingface_token: str | None
    """Reserved for the planned Hugging Face adapter; currently unused."""

    github_token: str | None
    """GitHub token used only to increase rate limits for public release feeds."""

    # ───── Behavior ─────
    dataset_output_path: Path
    """Where to write the final dataset.json."""

    log_level: str
    """DEBUG / INFO / WARNING / ERROR."""

    pipeline_mode: str
    """Logged mode label; 'quick' does not currently skip any adapters."""

    # ───── Network ─────
    http_timeout_seconds: float
    """HTTP request timeout in seconds."""

    http_max_retries: int
    """Maximum retries with exponential backoff."""

    @classmethod
    def load(cls) -> "Config":
        repo_root = Path(__file__).resolve().parent.parent.parent
        default_output = repo_root / "dataset" / "dataset.json"

        return cls(
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
            artificial_analysis_api_key=(
                os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY") or None
            ),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
            huggingface_token=os.environ.get("HUGGINGFACE_TOKEN") or None,
            github_token=(
                os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
                or os.environ.get("GITHUB_TOKEN")
                or None
            ),
            dataset_output_path=Path(
                os.environ.get("DATASET_OUTPUT_PATH") or str(default_output)
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            pipeline_mode=os.environ.get("PIPELINE_MODE", "full"),
            http_timeout_seconds=float(
                os.environ.get("HTTP_TIMEOUT_SECONDS", "30")
            ),
            http_max_retries=int(os.environ.get("HTTP_MAX_RETRIES", "3")),
        )

    def has_key(self, key_name: str) -> bool:
        """Check whether a given API key is available."""
        value = getattr(self, key_name, None)
        return bool(value)


config = Config.load()
