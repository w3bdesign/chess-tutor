"""Live integration test against chess-api.com (opt-in).

Skipped by default to keep the suite offline/fast. Enable with:

    RUN_LIVE_TESTS=1 pytest -m live

It confirms the real WebSocket surface still streams top-N candidates with the
fields this provider depends on.
"""

from __future__ import annotations

import os

import pytest

from chess_tutor.engine.chess_api import ChessApiProvider

pytestmark = pytest.mark.live

STARTPOS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1",
    reason="Set RUN_LIVE_TESTS=1 to run live chess-api.com integration tests.",
)
def test_live_startpos_returns_candidates() -> None:
    provider = ChessApiProvider()
    with provider:
        analysis = provider.analyse(STARTPOS, multipv=3, depth=12)

    assert analysis.best is not None
    assert 1 <= len(analysis.candidates) <= 3
    # Ranks are contiguous and best-first.
    assert [c.rank for c in analysis.candidates] == list(
        range(1, len(analysis.candidates) + 1)
    )
    # Best-first ordering holds.
    keys = [c.sort_key() for c in analysis.candidates]
    assert keys == sorted(keys, reverse=True)
    # Each candidate carries a concrete move.
    for c in analysis.candidates:
        assert c.move_uci
