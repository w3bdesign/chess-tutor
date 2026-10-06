"""Unit tests for environment-driven configuration."""

from __future__ import annotations

import pytest

from chess_tutor import config as config_module
from chess_tutor.config import Settings, load_settings


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure config-relevant env vars start unset for each test."""
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "CHESS_API_WS_URL",
        "CHESS_API_DEPTH",
        "MULTIPV",
        "BLUNDER_THRESHOLD_CP",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings()
    assert settings.openai_api_key is None
    assert settings.openai_base_url.startswith("https://")
    assert settings.openai_model == "gemini-3.1-pro-preview"
    assert settings.chess_api_ws_url == "wss://chess-api.com/v1"
    assert settings.chess_api_depth == 13
    assert settings.multipv == 3
    assert settings.blunder_threshold_cp == 80


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "custom-model")
    monkeypatch.setenv("CHESS_API_DEPTH", "18")
    monkeypatch.setenv("MULTIPV", "5")
    settings = load_settings()
    assert settings.openai_api_key == "sk-test"
    assert settings.openai_model == "custom-model"
    assert settings.chess_api_depth == 18
    assert settings.multipv == 5


def test_has_llm_true_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert load_settings().has_llm is True


def test_has_llm_false_when_key_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_settings().has_llm is False


def test_invalid_int_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHESS_API_DEPTH", "not-a-number")
    assert load_settings().chess_api_depth == 13


def test_blank_int_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MULTIPV", "   ")
    assert load_settings().multipv == 3


def test_empty_api_key_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert load_settings().openai_api_key is None


def test_settings_is_frozen() -> None:
    settings = Settings(
        openai_api_key=None,
        openai_base_url="https://example.com",
        openai_model="m",
        chess_api_ws_url="wss://example.com",
        chess_api_depth=12,
        multipv=3,
        blunder_threshold_cp=80,
    )
    with pytest.raises(Exception):
        settings.multipv = 5  # type: ignore[misc]


def test_module_loads_dotenv_on_import() -> None:
    # load_settings relies on python-dotenv having been imported at module load.
    assert hasattr(config_module, "load_dotenv")
