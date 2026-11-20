"""One Lichess game against a bot, driven on a background thread.

:class:`LichessGame` challenges a bot, waits for it to accept, then follows the
game's NDJSON stream and publishes immutable :class:`GameSnapshot` objects
(moves, clocks, status). The GUI controller polls :meth:`LichessGame.snapshot`
or blocks on :meth:`LichessGame.wait_for_move_count` from its own worker thread,
so the render loop never waits on the network.

The client is injected, so the whole flow is unit-testable with a fake client
and fake streams (no network).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol

import chess

from .client import LichessError

# Statuses during which the game is still live (anything else = finished/failed).
_ACTIVE = {"connecting", "created", "started"}
_MAX_RECONNECTS = 3


class EventStream(Protocol):
    @property
    def ended(self) -> bool: ...
    def get(self, timeout: float) -> dict[str, Any] | None: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class GameSnapshot:
    """Immutable view of the Lichess game at one instant."""

    status: str = "connecting"  # connecting|created|started|mate|resign|...|declined|error
    game_id: str | None = None
    moves: tuple[str, ...] = ()
    wtime_ms: int | None = None
    btime_ms: int | None = None
    received_at: float = 0.0  # monotonic time the clocks were reported
    winner: str | None = None  # "white" | "black" | None
    message: str = ""  # human-readable error / decline reason

    @property
    def is_over(self) -> bool:
        return self.status not in _ACTIVE

    @property
    def is_started(self) -> bool:
        return self.status == "started"


def live_clocks(snap: GameSnapshot, now: float) -> tuple[int | None, int | None]:
    """Return ``(white_ms, black_ms)`` with the running side's clock ticked down.

    Lichess only starts the clocks after both sides have made their first move.
    """
    w, b = snap.wtime_ms, snap.btime_ms
    if not snap.is_started or len(snap.moves) < 2 or w is None or b is None:
        return w, b
    elapsed = max(0, int((now - snap.received_at) * 1000))
    if len(snap.moves) % 2 == 0:
        w = max(0, w - elapsed)
    else:
        b = max(0, b - elapsed)
    return w, b


def format_clock(ms: int | None) -> str:
    """``mm:ss`` (or ``h:mm:ss``) for a clock in milliseconds; ``--:--`` if unknown."""
    if ms is None:
        return "--:--"
    total = max(0, ms) // 1000
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def describe_end(snap: GameSnapshot, *, bot: str, human_color: chess.Color) -> str:
    """Plain-English result line for a finished (or failed) game."""
    human = "white" if human_color == chess.WHITE else "black"

    def name(color: str | None) -> str:
        if color is None:
            return "?"
        return "You" if color == human else bot

    winner = snap.winner
    loser = None if winner is None else ("black" if winner == "white" else "white")
    status = snap.status
    if status == "mate":
        return f"Checkmate - {name(winner)} won."
    if status == "resign":
        return f"{name(loser)} resigned - {name(winner)} won."
    if status in ("outoftime", "timeout"):
        return f"{name(loser)} ran out of time - {name(winner)} won."
    if status == "stalemate":
        return "Draw by stalemate."
    if status == "draw":
        return "Draw."
    if status in ("aborted", "noStart"):
        return "Game aborted on Lichess (e.g. no first move in time). Press N for a new game."
    if status in ("declined", "error"):
        return snap.message or f"Lichess game failed ({status})."
    return f"Game over ({status})."


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _game_id(event: dict[str, Any]) -> str | None:
    game = event.get("game") or {}
    return game.get("gameId") or game.get("id")


class LichessGame:
    """A single casual game against ``bot`` on Lichess (Board API)."""

    def __init__(
        self,
        client: Any,
        *,
        bot: str,
        human_color: chess.Color,
        clock_limit_s: int,
        increment_s: int,
        accept_timeout_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self.bot = bot
        self.human_color = human_color
        self._clock_limit_s = clock_limit_s
        self._increment_s = increment_s
        self._accept_timeout_s = accept_timeout_s
        self._clock = clock
        self._snap = GameSnapshot()
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending_challenge: str | None = None

    # -- public API ----------------------------------------------------------- #
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def snapshot(self) -> GameSnapshot:
        with self._cond:
            return self._snap

    def wait_for_move_count(self, count: int, timeout: float) -> GameSnapshot:
        """Block until ``count`` moves exist, the game ends, or ``timeout`` passes."""
        with self._cond:
            self._cond.wait_for(
                lambda: len(self._snap.moves) >= count
                or self._snap.is_over
                or self._stop.is_set(),
                timeout=timeout,
            )
            return self._snap

    def send_move(self, uci: str) -> None:
        """Play ``uci`` in the Lichess game (raises :class:`LichessError`)."""
        game_id = self.snapshot().game_id
        if not game_id:
            raise LichessError("The Lichess game has not started yet.")
        self._client.make_move(game_id, uci)

    def stop(self) -> None:
        """Leave the game: abort if still abortable, else resign. Never raises."""
        self._stop.set()
        snap = self.snapshot()
        try:
            if snap.game_id and not snap.is_over:
                if len(snap.moves) < 2:
                    try:
                        self._client.abort(snap.game_id)
                    except LichessError:
                        self._client.resign(snap.game_id)
                else:
                    self._client.resign(snap.game_id)
            elif self._pending_challenge:
                self._client.cancel_challenge(self._pending_challenge)
        except LichessError:
            pass
        with self._cond:
            self._cond.notify_all()

    # -- background thread ---------------------------------------------------- #
    def _update(self, **changes: Any) -> None:
        with self._cond:
            self._snap = replace(self._snap, **changes)
            self._cond.notify_all()

    def _run(self) -> None:
        try:
            game_id = self._connect()
            if game_id is not None:
                self._follow(game_id)
        except LichessError as exc:
            self._update(status="error", message=str(exc))
        except Exception as exc:  # noqa: BLE001 - never kill the UI over this
            self._update(status="error", message=f"Unexpected Lichess error: {exc}")

    def _connect(self) -> str | None:
        """Challenge the bot and wait for it to accept; return the game id."""
        events = self._client.stream_events()
        try:
            # Subscribe first, so the bot's "gameStart" can't arrive before we listen.
            connected = getattr(events, "connected", None)
            if connected is not None:
                connected.wait(timeout=10)
            color = "white" if self.human_color == chess.WHITE else "black"
            cid = self._client.challenge(
                self.bot,
                color=color,
                clock_limit_s=self._clock_limit_s,
                increment_s=self._increment_s,
            )
            self._pending_challenge = cid
            self._update(message=f"challenge sent, waiting for {self.bot} to accept...")
            deadline = self._clock() + self._accept_timeout_s
            next_check = self._clock() + 3.0
            while not self._stop.is_set():
                # Fallback: if the event was missed, the game still shows up here.
                if self._clock() >= next_check and hasattr(self._client, "ongoing_game_ids"):
                    next_check = self._clock() + 3.0
                    try:
                        if cid in self._client.ongoing_game_ids():
                            break
                    except LichessError:
                        pass
                remaining = deadline - self._clock()
                if remaining <= 0:
                    try:
                        self._client.cancel_challenge(cid)
                    except LichessError:
                        pass
                    self._update(
                        status="declined",
                        message=f"{self.bot} did not answer within "
                        f"{self._accept_timeout_s:.0f}s. Press N to retry.",
                    )
                    return None
                event = events.get(min(remaining, 0.5))
                if event is None:
                    if events.ended:
                        raise LichessError("The Lichess event stream closed unexpectedly.")
                    continue
                kind = event.get("type")
                if kind == "gameStart" and _game_id(event) == cid:
                    break
                if kind in ("challengeDeclined", "challengeCanceled"):
                    challenge = event.get("challenge") or {}
                    if challenge.get("id") == cid:
                        reason = (
                            challenge.get("declineReason")
                            or challenge.get("declineReasonKey")
                            or kind
                        )
                        self._update(
                            status="declined",
                            message=f"{self.bot} declined the challenge: {reason}",
                        )
                        return None
            else:
                return None
        finally:
            events.close()
        self._pending_challenge = None
        self._update(status="created", game_id=cid, message="")
        return cid

    def _follow(self, game_id: str) -> None:
        """Mirror the game stream into snapshots until the game ends or we stop."""
        reconnects = 0
        while not self._stop.is_set():
            stream = self._client.stream_game(game_id)
            try:
                while not self._stop.is_set():
                    event = stream.get(0.5)
                    if event is None:
                        if stream.ended:
                            break
                        continue
                    self._apply(event)
                    if self.snapshot().is_over:
                        return
            finally:
                stream.close()
            if self._stop.is_set():
                return
            reconnects += 1
            if reconnects > _MAX_RECONNECTS:
                self._update(status="error", message="Lost the connection to the Lichess game.")
                return
            self._stop.wait(1.0)

    def _apply(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "gameFull":
            state = event.get("state") or {}
        elif kind == "gameState":
            state = event
        else:
            return  # chatLine, opponentGone, ...
        self._update(
            status=str(state.get("status") or "started"),
            moves=tuple(str(state.get("moves") or "").split()),
            wtime_ms=_as_int(state.get("wtime")),
            btime_ms=_as_int(state.get("btime")),
            received_at=self._clock(),
            winner=state.get("winner"),
        )
