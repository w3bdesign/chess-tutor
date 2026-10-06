"""Unit tests for the CLI's pure rendering/parsing helpers (no terminal/network)."""

from __future__ import annotations

import chess

from chess_tutor.cli.main import (
    _choose_color,
    _resolve_user_move,
    _with_depth,
    build_comparison_table,
    format_decision_tag,
    render_board,
)
from chess_tutor.config import load_settings
from chess_tutor.engine.hybrid import (
    SOURCE_ENGINE_ONLY,
    SOURCE_ENGINE_VETO,
    SOURCE_LLM,
    MoveDecision,
)
from chess_tutor.engine.models import Analysis, CandidateLine
from chess_tutor.engine.teaching import comparison_rows


def _analysis() -> Analysis:
    return Analysis(
        fen=chess.STARTING_FEN,
        candidates=[
            CandidateLine(move_uci="e2e4", move_san="e4", score_cp=30, rank=1),
            CandidateLine(move_uci="d2d4", move_san="d4", score_cp=20, rank=2),
        ],
        depth=13,
    )


class TestRenderBoard:
    def test_white_perspective_rank_order(self) -> None:
        board = chess.Board()
        text = render_board(board, perspective=chess.WHITE)
        lines = text.splitlines()
        # First board row is rank 8, last labelled row is files a-h.
        assert lines[0].startswith("8")
        assert lines[-2].startswith("1")
        assert lines[-1].strip().startswith("a")

    def test_black_perspective_flips(self) -> None:
        board = chess.Board()
        text = render_board(board, perspective=chess.BLACK)
        lines = text.splitlines()
        assert lines[0].startswith("1")
        assert lines[-1].strip().startswith("h")

    def test_contains_piece_glyphs(self) -> None:
        text = render_board(chess.Board())
        assert "♔" in text or "♚" in text


class TestResolveUserMove:
    def test_parses_san(self) -> None:
        board = chess.Board()
        move = _resolve_user_move(board, "Nf3")
        assert move == chess.Move.from_uci("g1f3")

    def test_parses_uci(self) -> None:
        board = chess.Board()
        move = _resolve_user_move(board, "e2e4")
        assert move == chess.Move.from_uci("e2e4")

    def test_rejects_illegal(self) -> None:
        board = chess.Board()
        assert _resolve_user_move(board, "e2e5") is None

    def test_rejects_garbage(self) -> None:
        board = chess.Board()
        assert _resolve_user_move(board, "xyz") is None

    def test_empty_is_none(self) -> None:
        assert _resolve_user_move(chess.Board(), "   ") is None


class TestChooseColor:
    def test_white(self) -> None:
        assert _choose_color("white") == chess.WHITE

    def test_black(self) -> None:
        assert _choose_color("black") == chess.BLACK

    def test_default_on_unknown(self) -> None:
        assert _choose_color("purple") == chess.WHITE

    def test_random_returns_a_color(self) -> None:
        assert _choose_color("random") in (chess.WHITE, chess.BLACK)


class TestWithDepth:
    def test_overrides_depth(self) -> None:
        settings = load_settings()
        updated = _with_depth(settings, 18)
        assert updated.chess_api_depth == 18
        # other fields preserved
        assert updated.multipv == settings.multipv

    def test_floors_at_one(self) -> None:
        settings = load_settings()
        assert _with_depth(settings, 0).chess_api_depth == 1


class TestFormatDecisionTag:
    def _decision(self, source: str) -> MoveDecision:
        return MoveDecision(
            move_uci="e2e4",
            source=source,
            vetoed=False,
            reason="",
            loss_cp=0,
            analysis=_analysis(),
        )

    def test_llm_tag(self) -> None:
        assert format_decision_tag(self._decision(SOURCE_LLM)) == "[coach]"

    def test_veto_tag(self) -> None:
        assert format_decision_tag(self._decision(SOURCE_ENGINE_VETO)) == "[engine veto]"

    def test_engine_only_tag(self) -> None:
        assert format_decision_tag(self._decision(SOURCE_ENGINE_ONLY)) == "[engine only]"


class TestBuildComparisonTable:
    def test_renders_row_per_candidate(self) -> None:
        rows = comparison_rows(_analysis(), chosen_uci="e2e4")
        table = build_comparison_table(rows)
        assert table.row_count == 2
        # Expected columns: #, Move, Eval, Loss, Line, Coach's note
        assert len(table.columns) == 6
