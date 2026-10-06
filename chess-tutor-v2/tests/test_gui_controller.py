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

from chess_tutor.gui.controller import GameController


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
