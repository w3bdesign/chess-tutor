"""Environment-driven configuration for Chess Tutor v2.

All runtime knobs live here so the engine, teaching layer, and CLI share a
single source of truth. Values are read from environment variables (optionally
loaded from a local ``.env`` file via python-dotenv).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env if present; real environment variables always win.
load_dotenv()


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Resolved application settings."""

    # LLM (the brain), OpenAI-compatible
    openai_api_key: str | None
    openai_base_url: str
    openai_model: str

    # Chess engine analysis (the authority)
    chess_api_url: str
    chess_api_depth: int

    # Analysis / guardrails
    multipv: int
    blunder_threshold_cp: int

    @property
    def has_llm(self) -> bool:
        """True when an LLM key is configured.

        When False, the engine degrades gracefully to pure engine play with
        template-based coaching, so the POC still runs without an LLM key.
        """
        return bool(self.openai_api_key)


def load_settings() -> Settings:
    """Build a :class:`Settings` instance from the current environment."""
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_base_url=os.getenv(
            "OPENAI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
        openai_model=os.getenv("OPENAI_MODEL", "gemini-3.1-pro-preview"),
        chess_api_url=os.getenv("CHESS_API_URL", "https://chess-api.com/v1"),
        chess_api_depth=_get_int("CHESS_API_DEPTH", 13),
        multipv=_get_int("MULTIPV", 3),
        blunder_threshold_cp=_get_int("BLUNDER_THRESHOLD_CP", 80),
    )
