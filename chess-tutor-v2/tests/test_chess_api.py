"""Unit tests for chess-api.com message parsing and aggregation.

These exercise the pure helper functions (no network). A separate, network-gated
integration test lives in ``test_chess_api_live.py``.
"""

from __future__ import annotations

from chess_tutor.engine.chess_api import (
    _build_analysis,
    _candidate_from_message,
    _side_to_move_is_white,
)

STARTPOS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
BLACK_TO_MOVE = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


class TestSideToMove:
    def test_white_to_move(self) -> None:
        assert _side_to_move_is_white(STARTPOS) is True

    def test_black_to_move(self) -> None:
        assert _side_to_move_is_white(BLACK_TO_MOVE) is False

    def test_malformed_fen_defaults_white(self) -> None:
        assert _side_to_move_is_white("garbage") is True


class TestCandidateFromMessage:
    def test_white_centipawns_unchanged(self) -> None:
        msg = {"move": "e2e4", "san": "e4", "centipawns": 35, "depth": 12}
        line = _candidate_from_message(msg, white_to_move=True)
        assert line is not None
        assert line.move_uci == "e2e4"
        assert line.move_san == "e4"
        assert line.score_cp == 35
        assert line.mate is None

    def test_black_centipawns_negated(self) -> None:
        # White-perspective +50 means Black (to move) is worse: -50 side-to-move.
        msg = {"move": "e7e5", "centipawns": 50}
        line = _candidate_from_message(msg, white_to_move=False)
        assert line is not None
        assert line.score_cp == -50

    def test_eval_pawns_converted_to_centipawns(self) -> None:
        msg = {"move": "e2e4", "eval": 1.5}
        line = _candidate_from_message(msg, white_to_move=True)
        assert line is not None
        assert line.score_cp == 150

    def test_centipawns_preferred_over_eval(self) -> None:
        msg = {"move": "e2e4", "centipawns": 42, "eval": 9.9}
        line = _candidate_from_message(msg, white_to_move=True)
        assert line is not None
        assert line.score_cp == 42

    def test_mate_white_perspective_unchanged(self) -> None:
        msg = {"move": "d1h5", "mate": 3}
        line = _candidate_from_message(msg, white_to_move=True)
        assert line is not None
        assert line.mate == 3
        assert line.score_cp is None

    def test_mate_negated_for_black(self) -> None:
        # White mates in 2 => Black (to move) is getting mated: -2.
        msg = {"move": "a7a6", "mate": 2}
        line = _candidate_from_message(msg, white_to_move=False)
        assert line is not None
        assert line.mate == -2

    def test_pv_from_continuation_arr(self) -> None:
        msg = {"move": "e2e4", "centipawns": 20, "continuationArr": ["e7e5", "g1f3"]}
        line = _candidate_from_message(msg, white_to_move=True)
        assert line is not None
        assert line.pv == ["e7e5", "g1f3"]

    def test_missing_move_returns_none(self) -> None:
        assert _candidate_from_message({"centipawns": 10}, white_to_move=True) is None

    def test_non_list_pv_ignored(self) -> None:
        msg = {"move": "e2e4", "centipawns": 20, "continuationArr": "oops"}
        line = _candidate_from_message(msg, white_to_move=True)
        assert line is not None
        assert line.pv == []


class TestBuildAnalysis:
    def test_keeps_deepest_message_per_move(self) -> None:
        messages = [
            {"type": "move", "move": "e2e4", "centipawns": 10, "depth": 6},
            {"type": "move", "move": "e2e4", "centipawns": 30, "depth": 12},
        ]
        analysis = _build_analysis(STARTPOS, messages, multipv=3)
        assert len(analysis.candidates) == 1
        assert analysis.candidates[0].score_cp == 30
        assert analysis.depth == 12

    def test_sorts_best_first_and_ranks(self) -> None:
        messages = [
            {"type": "move", "move": "a2a3", "centipawns": 5, "depth": 12},
            {"type": "move", "move": "e2e4", "centipawns": 40, "depth": 12},
            {"type": "bestmove", "move": "d2d4", "centipawns": 25, "depth": 12},
        ]
        analysis = _build_analysis(STARTPOS, messages, multipv=3)
        assert [c.move_uci for c in analysis.candidates] == ["e2e4", "d2d4", "a2a3"]
        assert [c.rank for c in analysis.candidates] == [1, 2, 3]

    def test_truncates_to_multipv(self) -> None:
        messages = [
            {"type": "move", "move": f"m{i}", "centipawns": i, "depth": 12}
            for i in range(5)
        ]
        analysis = _build_analysis(STARTPOS, messages, multipv=3)
        assert len(analysis.candidates) == 3

    def test_graceful_degrade_fewer_lines(self) -> None:
        messages = [
            {"type": "bestmove", "move": "e2e4", "centipawns": 20, "depth": 12},
        ]
        analysis = _build_analysis(STARTPOS, messages, multipv=3)
        assert len(analysis.candidates) == 1

    def test_ignores_non_move_messages(self) -> None:
        messages = [
            {"type": "info", "depth": 1},
            {"type": "move", "depth": 8},  # no move field
            {"type": "move", "move": "e2e4", "centipawns": 20, "depth": 12},
        ]
        analysis = _build_analysis(STARTPOS, messages, multipv=3)
        assert len(analysis.candidates) == 1
        assert analysis.candidates[0].move_uci == "e2e4"

    def test_empty_messages_yield_no_candidates(self) -> None:
        analysis = _build_analysis(STARTPOS, [], multipv=3)
        assert analysis.candidates == []
        assert analysis.best is None

    def test_black_to_move_normalizes_ordering(self) -> None:
        # White-perspective evals; for Black to move, the line that is most
        # negative for White (best for Black) should rank first.
        messages = [
            {"type": "move", "move": "e7e5", "centipawns": -30, "depth": 12},
            {"type": "move", "move": "a7a6", "centipawns": 20, "depth": 12},
        ]
        analysis = _build_analysis(BLACK_TO_MOVE, messages, multipv=3)
        # e7e5 (White -30 -> Black +30) is best for the side to move.
        assert analysis.candidates[0].move_uci == "e7e5"
        assert analysis.candidates[0].score_cp == 30
