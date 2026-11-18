"""Offline tests for the Lichess session and its GameController integration.

Everything here uses fakes -- no network, no real Lichess account.
"""

from __future__ import annotations

from dataclasses import replace

import chess
import pytest

from chess_tutor.gui.controller import GameController
from chess_tutor.lichess.client import LichessClient, LichessError
from chess_tutor.lichess.session import (
    GameSnapshot,
    LichessGame,
    describe_end,
    format_clock,
    live_clocks,
)


# --------------------------------------------------------------------------- #
# Fakes for the session (client + NDJSON streams)
# --------------------------------------------------------------------------- #
class _FakeStream:
    def __init__(self, events: list[dict]) -> None:
        self._events = list(events)
        self.closed = False

    @property
    def ended(self) -> bool:
        return not self._events

    def get(self, timeout: float) -> dict | None:
        return self._events.pop(0) if self._events else None

    def close(self) -> None:
        self.closed = True


class _FakeClient:
    def __init__(self, events: list[dict], game_events: list[dict]) -> None:
        self.events = events
        self.game_events = game_events
        self.calls: list[tuple] = []

    def stream_events(self) -> _FakeStream:
        return _FakeStream(self.events)

    def challenge(self, username, *, color, clock_limit_s, increment_s) -> str:
        self.calls.append(("challenge", username, color, clock_limit_s, increment_s))
        return "g1"

    def cancel_challenge(self, cid) -> None:
        self.calls.append(("cancel", cid))

    def stream_game(self, game_id) -> _FakeStream:
        return _FakeStream(self.game_events)

    def make_move(self, game_id, uci) -> None:
        self.calls.append(("move", game_id, uci))

    def abort(self, game_id) -> None:
        self.calls.append(("abort", game_id))

    def resign(self, game_id) -> None:
        self.calls.append(("resign", game_id))


def _game(client, **kw) -> LichessGame:
    return LichessGame(
        client,
        bot="maia5",
        human_color=chess.WHITE,
        clock_limit_s=1800,
        increment_s=0,
        **kw,
    )


def _run(game: LichessGame) -> GameSnapshot:
    game.start()
    assert game._thread is not None
    game._thread.join(timeout=5)
    return game.snapshot()


def test_client_requires_token() -> None:
    with pytest.raises(LichessError):
        LichessClient("")


def test_session_follows_game_to_the_end() -> None:
    client = _FakeClient(
        events=[{"type": "gameStart", "game": {"gameId": "g1"}}],
        game_events=[
            {"type": "gameFull", "state": {"status": "started", "moves": "", "wtime": 1800000, "btime": 1800000}},
            {"type": "gameState", "status": "started", "moves": "e2e4 e7e5", "wtime": 1799000, "btime": 1798000},
            {"type": "gameState", "status": "mate", "moves": "e2e4 e7e5 d1h5 b8c6 f1c4 g8f6 h5f7", "winner": "white"},
        ],
    )
    snap = _run(_game(client))
    assert client.calls[0] == ("challenge", "maia5", "white", 1800, 0)
    assert snap.game_id == "g1"
    assert snap.status == "mate" and snap.is_over
    assert snap.moves[-1] == "h5f7"
    assert snap.winner == "white"


def test_session_reports_decline() -> None:
    client = _FakeClient(
        events=[
            {
                "type": "challengeDeclined",
                "challenge": {"id": "g1", "declineReason": "This time control is not accepted."},
            }
        ],
        game_events=[],
    )
    snap = _run(_game(client))
    assert snap.status == "declined"
    assert "not accepted" in snap.message


def test_session_times_out_and_cancels() -> None:
    client = _FakeClient(events=[{"type": "keepalive"}] * 3, game_events=[])
    ticks = iter([0.0, 0.0, 5.0, 100.0, 100.0, 100.0])
    snap = _run(_game(client, accept_timeout_s=10, clock=lambda: next(ticks, 100.0)))
    assert snap.status == "declined"
    assert ("cancel", "g1") in client.calls


def test_stop_aborts_early_and_resigns_later() -> None:
    client = _FakeClient(events=[], game_events=[])
    game = _game(client)
    game._snap = GameSnapshot(status="started", game_id="g1", moves=("e2e4",))
    game.stop()
    assert ("abort", "g1") in client.calls

    client2 = _FakeClient(events=[], game_events=[])
    game2 = _game(client2)
    game2._snap = GameSnapshot(status="started", game_id="g1", moves=("e2e4", "e7e5"))
    game2.stop()
    assert ("resign", "g1") in client2.calls


def test_live_clocks_ticks_side_to_move_only() -> None:
    snap = GameSnapshot(
        status="started", moves=("e2e4", "e7e5"), wtime_ms=60000, btime_ms=60000, received_at=10.0
    )
    assert live_clocks(snap, 12.5) == (57500, 60000)  # white to move
    snap_b = replace(snap, moves=("e2e4", "e7e5", "g1f3"))
    assert live_clocks(snap_b, 12.5) == (60000, 57500)
    # Clocks don't run before both sides have moved.
    assert live_clocks(replace(snap, moves=("e2e4",)), 99.0) == (60000, 60000)


def test_format_clock() -> None:
    assert format_clock(None) == "--:--"
    assert format_clock(65_000) == "01:05"
    assert format_clock(3_725_000) == "1:02:05"


def test_describe_end() -> None:
    snap = GameSnapshot(status="resign", winner="white")
    assert describe_end(snap, bot="maia5", human_color=chess.WHITE) == "maia5 resigned - You won."
    snap = GameSnapshot(status="mate", winner="black")
    assert "maia5 won" in describe_end(snap, bot="maia5", human_color=chess.WHITE)


# --------------------------------------------------------------------------- #
# GameController with a fake Lichess game
# --------------------------------------------------------------------------- #
class _Engine:
    def select_move(self, fen, *, analysis=None):  # pragma: no cover - must not be used
        raise AssertionError("local engine must not move in Lichess mode")

    def analyse(self, fen):  # pragma: no cover
        raise AssertionError("not used")


class _FakeGame:
    bot = "maia5"

    def __init__(self, snap: GameSnapshot, *, reply: str | None = None, fail: bool = False):
        self.snap = snap
        self.reply = reply
        self.fail = fail
        self.sent: list[str] = []
        self.started = False
        self.stopped = False
        self.stop_called = False

    def start(self) -> None:
        self.started = True

    def snapshot(self) -> GameSnapshot:
        return self.snap

    def send_move(self, uci: str) -> None:
        if self.fail:
            raise LichessError("Lichess HTTP 400: illegal move")
        self.sent.append(uci)
        moves = self.snap.moves + (uci,) + ((self.reply,) if self.reply else ())
        self.snap = replace(self.snap, moves=moves)

    def wait_for_move_count(self, count: int, timeout: float) -> GameSnapshot:
        return self.snap

    def stop(self) -> None:
        self.stop_called = True
        self.stopped = True


def _controller(game: _FakeGame, human=chess.WHITE) -> GameController:
    return GameController(_Engine(), human_color=human, lichess=game)  # type: ignore[arg-type]


def _join(ctrl: GameController) -> None:
    if ctrl._worker is not None:
        ctrl._worker.join(timeout=5)


def test_not_human_turn_while_connecting() -> None:
    game = _FakeGame(GameSnapshot())
    ctrl = _controller(game)
    assert game.started
    assert ctrl.state.status.startswith("Connecting")
    assert not ctrl.is_human_turn
    assert not ctrl.should_start_tutor_turn  # it's White (human) to move


def test_poll_switches_status_once_game_starts() -> None:
    game = _FakeGame(GameSnapshot())
    ctrl = _controller(game)
    game.snap = GameSnapshot(status="started", game_id="g1")
    ctrl.poll_lichess()
    assert ctrl.state.status == "Your move."
    assert ctrl.is_human_turn


def test_player_move_is_forwarded_and_bot_reply_applied() -> None:
    game = _FakeGame(GameSnapshot(status="started", game_id="g1"), reply="e7e5")
    ctrl = _controller(game)
    assert ctrl.try_player_move(chess.E2, chess.E4)
    _join(ctrl)
    assert game.sent == ["e2e4"]
    assert [m.uci() for m in ctrl.board.move_stack] == ["e2e4", "e7e5"]
    assert ctrl.state.headline == "maia5 played e5."
    assert ctrl.state.status == "Your move."
    assert ctrl.is_human_turn


def test_rejected_move_is_taken_back() -> None:
    game = _FakeGame(GameSnapshot(status="started", game_id="g1"), fail=True)
    ctrl = _controller(game)
    assert ctrl.try_player_move(chess.E2, chess.E4)
    _join(ctrl)
    assert ctrl.board.move_stack == []
    assert "rejected" in ctrl.state.status


def test_bot_moves_first_when_human_is_black() -> None:
    game = _FakeGame(GameSnapshot(status="started", game_id="g1", moves=("d2d4",)))
    ctrl = _controller(game, human=chess.BLACK)
    assert ctrl.should_start_tutor_turn
    ctrl.start_tutor_turn()
    _join(ctrl)
    assert [m.uci() for m in ctrl.board.move_stack] == ["d2d4"]
    assert ctrl.is_human_turn


def test_poll_detects_resignation_and_timeout() -> None:
    game = _FakeGame(GameSnapshot(status="started", game_id="g1"))
    ctrl = _controller(game)
    game.snap = replace(game.snap, status="outoftime", winner="black")
    ctrl.poll_lichess()
    assert ctrl.state.game_over
    assert "ran out of time" in ctrl.state.narrative
    assert not ctrl.is_human_turn


def test_close_stops_the_lichess_game() -> None:
    game = _FakeGame(GameSnapshot(status="started", game_id="g1"))
    ctrl = _controller(game)
    ctrl.close(wait=True)
    assert game.stop_called
    assert not ctrl.should_start_tutor_turn


def test_clock_texts_from_human_perspective() -> None:
    snap = GameSnapshot(status="started", game_id="g1", wtime_ms=60_000, btime_ms=30_000)
    ctrl = _controller(_FakeGame(snap), human=chess.BLACK)
    assert ctrl.clock_texts(now=0.0) == ("00:30", "01:00")
