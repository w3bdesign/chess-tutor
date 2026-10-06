"""Unit tests for the AnalysisProvider interface contract."""

from __future__ import annotations

import pytest

from chess_tutor.engine.models import Analysis, CandidateLine
from chess_tutor.engine.provider import AnalysisError, AnalysisProvider


def test_cannot_instantiate_abstract_provider() -> None:
    with pytest.raises(TypeError):
        AnalysisProvider()  # type: ignore[abstract]


class _FakeProvider(AnalysisProvider):
    """Minimal concrete provider for exercising the base-class behaviour."""

    def __init__(self) -> None:
        self.closed = False

    def analyse(self, fen: str, *, multipv: int, depth: int) -> Analysis:
        return Analysis(
            fen=fen,
            candidates=[CandidateLine(move_uci="e2e4", score_cp=30, rank=1)],
            depth=depth,
        )

    def close(self) -> None:
        self.closed = True


def test_concrete_provider_analyse() -> None:
    provider = _FakeProvider()
    analysis = provider.analyse("startpos", multipv=3, depth=12)
    assert analysis.best is not None
    assert analysis.best.move_uci == "e2e4"
    assert analysis.depth == 12


def test_context_manager_closes_provider() -> None:
    provider = _FakeProvider()
    with provider as p:
        assert p is provider
        assert provider.closed is False
    assert provider.closed is True


def test_default_close_is_noop() -> None:
    class _NoClose(AnalysisProvider):
        def analyse(self, fen: str, *, multipv: int, depth: int) -> Analysis:
            return Analysis(fen=fen, candidates=[])

    # Should not raise even though close() is not overridden.
    _NoClose().close()


def test_analysis_error_is_runtime_error() -> None:
    assert issubclass(AnalysisError, RuntimeError)
