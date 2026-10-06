"""Regression tests for the pygame-free game-flow logic in ``GameController``.

These tests pin down the *scheduling* decision that governs when the tutor's
background move is allowed to start. A real regression lived here: the pygame
render loop gated the tutor turn on ``state.thinking``, but a player move marks
the state ``thinking`` *before* any worker thread exists -- so the tutor turn was
never scheduled and the UI hung forever at "Tutor is thinking...".

The logic is now a pure predicate (:attr:`GameController.should_start_tutor_turn`)
that inspects only board/turn/busy state, so it is testable without a display,
a network, or the LLM. The dummy engine below is never actually called by the
predicate -- it exists purely to satisfy the constructor.
"""

from __future__ import annotations

import chess

from chess_tutor.engine.hybrid import MoveDecision
from chess_tutor.engine.models import Analysis, CandidateLine
from chess_tutor.gui.controller import GameController, _white_perspective_eval


class _DummyEngine:
    """Stand-in for :class:`HybridEngine`.

    ``should_start_tutor_turn`` never calls the engine, so these methods are only
    guards: if the predicate were to touch the engine, the test would fail loudly.
    """

    def select_move(self, fen: str):  # pragma: no cover - must not be called
        raise AssertionError("scheduling predicate must not call the engine")

    def close(self) -> None:  # pragma: no cover - not exercised here
        pass


def _controller(human_color: chess.Color = chess.WHITE) -> GameController:
    return GameController(_DummyEngine(), human_color=human_color)


def test_should_not_start_on_humans_turn_at_game_start() -> None:
    controller = _controller(human_color=chess.WHITE)
    # White (the human) is to move from the opening position.
    assert controller.is_human_turn is True
    assert controller.should_start_tutor_turn is False


def test_should_start_after_player_move_even_while_thinking_flag_set() -> None:
    """The exact hang scenario: after a player move the state is ``thinking`` but
    no worker exists yet, and the tutor turn MUST still be schedulable."""
    controller = _controller(human_color=chess.WHITE)

    assert controller.try_player_move(chess.E2, chess.E4) is True

    # The UI flag that previously (incorrectly) suppressed scheduling.
    assert controller.state.thinking is True
    # No worker thread has been spawned yet.
    assert controller.is_busy is False
    # It is now the tutor's turn, so the move must be schedulable.
    assert controller.is_human_turn is False
    assert controller.should_start_tutor_turn is True


def test_should_not_start_when_it_becomes_human_turn_again() -> None:
    """When the human is black, the opening position is the tutor's turn (ok),
    but once it's the human's turn the predicate must be False again."""
    controller = _controller(human_color=chess.BLACK)

    # White (the tutor) to move from the start -> schedulable.
    assert controller.is_human_turn is False
    assert controller.should_start_tutor_turn is True

    # Make a move for white so it becomes black's (the human's) turn.
    controller.board.push(chess.Move.from_uci("e2e4"))
    assert controller.is_human_turn is True
    assert controller.should_start_tutor_turn is False


def test_should_not_start_when_game_is_over() -> None:
    controller = _controller(human_color=chess.WHITE)
    # Fool's-mate position with black to move having been mated is awkward to set
    # up; instead drive the board into a checkmate and confirm no scheduling.
    for uci in ("f2f3", "e7e5", "g2g4", "d8h4"):  # 1. f3 e5 2. g4 Qh4#
        controller.board.push(chess.Move.from_uci(uci))
    assert controller.board.is_game_over() is True
    assert controller.should_start_tutor_turn is False


# -- proactive coaching for the side to move --------------------------------- #
class _CoachingEngine:
    """A stub that returns a canned decision so the coaching flow can be tested.

    Unlike :class:`_DummyEngine` this one *is* meant to be called -- but only via
    the coaching path, never via the tutor-scheduling predicate.
    """

    def __init__(self) -> None:
        self.calls = 0

    def select_move(self, fen: str) -> MoveDecision:
        self.calls += 1
        line = CandidateLine(
            move_uci="e2e4", move_san="e4", score_cp=30, pv=["e2e4", "e7e5"], rank=1
        )
        analysis = Analysis(fen=fen, candidates=[line])
        return MoveDecision(
            move_uci="e2e4",
            source="engine-only",
            vetoed=False,
            reason="Best by evaluation.",
            loss_cp=0,
            analysis=analysis,
        )

    def close(self) -> None:  # pragma: no cover - not exercised here
        pass


def test_should_coach_on_humans_turn_once_per_position() -> None:
    engine = _CoachingEngine()
    controller = GameController(engine, human_color=chess.WHITE)

    # It is the human's turn from the opening -> coaching should fire.
    assert controller.should_coach_side_to_move is True

    controller.coach_side_to_move()
    controller._coach_worker.join(timeout=2)

    # The coach produced a "your best" headline + candidate rows for the player.
    assert engine.calls == 1
    assert "Your best" in controller.state.headline
    assert controller.state.rows
    assert controller.state.thinking is False
    # Second poll for the *same* position must not re-fire (one pass per FEN).
    assert controller.should_coach_side_to_move is False


def test_should_not_coach_on_tutors_turn() -> None:
    engine = _CoachingEngine()
    controller = GameController(engine, human_color=chess.WHITE)
    # Advance to the tutor's turn; the tutor move path explains its own move.
    controller.board.push(chess.Move.from_uci("e2e4"))
    assert controller.is_human_turn is False
    assert controller.should_coach_side_to_move is False


def test_coaching_result_discarded_when_position_changed() -> None:
    engine = _CoachingEngine()
    controller = GameController(engine, human_color=chess.WHITE)
    stale_fen = controller.board.fen()
    # The player has already moved on to a different position.
    controller.board.push(chess.Move.from_uci("d2d4"))
    controller._run_coach_side_to_move(stale_fen)
    # Stale result must not clobber the panel with a headline for the old move.
    assert controller.state.headline == ""


def test_should_not_coach_when_game_is_over() -> None:
    engine = _CoachingEngine()
    controller = GameController(engine, human_color=chess.WHITE)
    for uci in ("f2f3", "e7e5", "g2g4", "d8h4"):  # 1. f3 e5 2. g4 Qh4#
        controller.board.push(chess.Move.from_uci(uci))
    assert controller.board.is_game_over() is True
    assert controller.should_coach_side_to_move is False


# -- White-perspective evaluation (powers the eval bar) ----------------------- #
def test_white_perspective_eval_keeps_sign_when_white_to_move() -> None:
    fen = chess.STARTING_FEN  # White to move.
    line = CandidateLine(move_uci="e2e4", score_cp=60, rank=1)
    cp, mate = _white_perspective_eval(Analysis(fen=fen, candidates=[line]))
    assert (cp, mate) == (60, None)


def test_white_perspective_eval_negates_when_black_to_move() -> None:
    board = chess.Board()
    board.push(chess.Move.from_uci("e2e4"))  # now Black to move.
    # +40 for the side to move (Black) is -40 from White's perspective.
    line = CandidateLine(move_uci="e7e5", score_cp=40, rank=1)
    cp, mate = _white_perspective_eval(Analysis(fen=board.fen(), candidates=[line]))
    assert (cp, mate) == (-40, None)


def test_white_perspective_eval_handles_mate_and_empty() -> None:
    board = chess.Board()
    board.push(chess.Move.from_uci("e2e4"))  # Black to move.
    line = CandidateLine(move_uci="d8h4", mate=2, rank=1)
    cp, mate = _white_perspective_eval(Analysis(fen=board.fen(), candidates=[line]))
    # A mate for Black (side to move) is a mate against White -> negative.
    assert (cp, mate) == (None, -2)
    # No candidates -> no evaluation.
    assert _white_perspective_eval(Analysis(fen=chess.STARTING_FEN, candidates=[])) == (
        None,
        None,
    )


def test_coaching_publishes_white_perspective_eval() -> None:
    engine = _CoachingEngine()  # returns score_cp=30 for the side to move.
    controller = GameController(engine, human_color=chess.WHITE)
    controller.coach_side_to_move()
    controller._coach_worker.join(timeout=2)
    # Opening position is White to move, so +30 stays +30 for White.
    assert controller.state.eval_cp == 30
    assert controller.state.eval_mate is None
