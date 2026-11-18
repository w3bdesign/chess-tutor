"""Threaded bridge between the Pygame UI and the :class:`HybridEngine`.

The UI must never block on the network (chess-api.com) or the LLM, so every
engine interaction runs on a background worker thread. Results are published back
as immutable :class:`CoachState` snapshots guarded by a lock; the render loop
simply reads the latest snapshot each frame.

This module imports **no pygame**, so the game-flow logic (whose turn it is, when
the tutor thinks, how a player move is validated) is unit-testable without a
display. All chess rules come from ``python-chess`` and all move selection from
the shared engine core -- nothing is reimplemented here (DRY).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import chess

from ..engine.hybrid import HybridEngine, MoveDecision
from ..engine.llm import LLMError
from ..engine.models import Analysis
from ..engine.provider import AnalysisError
from ..engine.teaching import ComparisonRow, comparison_rows, why_not_move, why_this_move
from ..explain.chat import ChatError, PositionChat, build_context, cited_squares
from ..explain.review import MoveReview, PositionCoaching, coach_position, review_move
from ..lichess.client import LichessError
from ..lichess.session import GameSnapshot, describe_end, format_clock, live_clocks

if TYPE_CHECKING:
    from ..lichess.session import LichessGame


@dataclass(frozen=True)
class CoachState:
    """Immutable snapshot of what the coaching panel should show."""

    status: str = "Your move."
    thinking: bool = False
    headline: str = ""  # e.g. "Tutor played Nf3 [coach]"
    narrative: str = ""  # why-this-move / why-not prose
    rows: tuple[ComparisonRow, ...] = ()
    last_move_uci: str | None = None  # for board highlight
    game_over: bool = False
    # Evaluation of the current position, normalized to **White's perspective**
    # (positive = good for White) so the TV-style eval bar can orient itself
    # regardless of whose turn it is. Both ``None`` until the first analysis.
    eval_cp: int | None = None
    eval_mate: int | None = None
    # Deterministic explanations (no LLM): the latest reviewed moves (oldest
    # first, at most two: the opponent's last move and yours) and coaching for
    # the position in front of the human.
    reviews: tuple[MoveReview, ...] = ()
    coaching: PositionCoaching | None = None
    coaching_fen: str | None = None
    # On-demand LLM chat about the current position: (role, text) pairs, the FEN
    # they belong to, squares cited in the last answer, and a busy flag.
    chat: tuple[tuple[str, str], ...] = ()
    chat_fen: str | None = None
    chat_marks: tuple[chess.Square, ...] = ()
    chat_busy: bool = False


def _white_perspective_eval(analysis: Analysis) -> tuple[int | None, int | None]:
    """Return ``(cp, mate)`` for ``analysis.best`` from **White's** perspective.

    Engine scores are stored relative to the side to move (bigger == better for
    whoever is about to play); the eval bar always orients itself to White, so we
    negate when it is Black's turn.
    """
    best = analysis.best
    if best is None:
        return None, None
    try:
        white_to_move = chess.Board(analysis.fen).turn == chess.WHITE
    except ValueError:
        white_to_move = True
    sign = 1 if white_to_move else -1
    cp = None if best.score_cp is None else sign * best.score_cp
    mate = None if best.mate is None else sign * best.mate
    return cp, mate


class GameController:
    """Owns the board, the engine, and the background worker for tutor moves."""

    def __init__(
        self,
        engine: HybridEngine,
        *,
        human_color: chess.Color = chess.WHITE,
        board: chess.Board | None = None,
        lichess: LichessGame | None = None,
        chat: PositionChat | None = None,
        analysis_headers: dict[str, str] | None = None,
    ) -> None:
        self._engine = engine
        self.chat_client = chat
        # Analysis mode: an imported game (PGN) is reviewed move by move; no play.
        self.analysis_mode = analysis_headers is not None
        self.headers: dict[str, str] = dict(analysis_headers or {})
        # Which position is shown: None = follow the latest move, else a ply count.
        self.view_ply: int | None = None
        self._view_cache: tuple[int, int, chess.Board] | None = None
        self.human_color = human_color
        self.board = board if board is not None else chess.Board()
        # Optional Lichess opponent (e.g. maia5). When set, the opponent's moves
        # come from Lichess instead of the local engine; the local engine is then
        # only used for coaching.
        self._lichess = lichess
        self._closed = False
        self._lock = threading.Lock()
        self._state = CoachState(status=self._initial_status())
        self._worker: threading.Thread | None = None
        # A *separate* worker for proactively coaching the side to move. It is
        # deliberately distinct from ``_worker`` so that coaching never sets
        # ``is_busy`` -- the human must be able to move at any instant, even while
        # the coach is still thinking about the current position.
        self._coach_worker: threading.Thread | None = None
        # The FEN we have already coached (or begun coaching), so we fire exactly
        # one coaching pass per position rather than once per frame.
        self._coached_fen: str | None = None
        # Shared engine analyses keyed by FEN: coaching, move reviews and
        # "why not?" all reuse one request per position.
        self._analyses: dict[str, Analysis] = {}
        self._inflight: dict[str, threading.Event] = {}
        self._analysis_lock = threading.Lock()
        self._reviews: dict[int, MoveReview] = {}

        if self._lichess is not None:
            self._lichess.start()
        if self.analysis_mode:
            self._state = CoachState(status="Analysing the imported game...")
            threading.Thread(target=self._review_all, daemon=True).start()

    # -- state access -------------------------------------------------------- #
    def _initial_status(self) -> str:
        if self._lichess is not None:
            return f"Connecting to Lichess ({self._lichess.bot})..."
        return "Your move." if self.human_color == chess.WHITE else "Tutor to move."

    @property
    def state(self) -> CoachState:
        with self._lock:
            return self._state

    def _set_state(self, **changes: object) -> None:
        with self._lock:
            self._state = replace(self._state, **changes)

    @property
    def opponent_name(self) -> str:
        return self._lichess.bot if self._lichess is not None else "Tutor"

    @property
    def lichess_snapshot(self) -> GameSnapshot | None:
        return self._lichess.snapshot() if self._lichess is not None else None

    def _lichess_ready(self) -> bool:
        """True when there is no Lichess game, or it is live and has an id."""
        if self._lichess is None:
            return True
        snap = self._lichess.snapshot()
        return bool(snap.game_id) and not snap.is_over

    # -- viewing earlier positions / imported games --------------------------- #
    @property
    def view_len(self) -> int:
        """Number of moves played in the position being shown."""
        n = len(self.board.move_stack)
        return n if self.view_ply is None else max(0, min(self.view_ply, n))

    @property
    def at_latest(self) -> bool:
        return self.view_len == len(self.board.move_stack)

    @property
    def view_board(self) -> chess.Board:
        n, v = len(self.board.move_stack), self.view_len
        if v == n:
            return self.board
        cached = self._view_cache
        if cached is not None and cached[0] == v and cached[1] == n:
            return cached[2]
        board = self.board.root()
        for move in self.board.move_stack[:v]:
            board.push(move)
        self._view_cache = (v, n, board)
        return board

    def step_view(self, delta: int) -> None:
        self.set_view(self.view_len + delta)

    def set_view(self, ply: int) -> None:
        n = len(self.board.move_stack)
        ply = max(0, min(ply, n))
        self.view_ply = None if ply >= n else ply

    def view_analysis(self) -> Analysis | None:
        with self._analysis_lock:
            return self._analyses.get(self.view_board.fen())

    def side_name(self, color: chess.Color) -> str:
        if self.analysis_mode:
            return self.headers.get("White" if color == chess.WHITE else "Black") or (
                "White" if color == chess.WHITE else "Black"
            )
        return "You" if color == self.human_color else self.opponent_name

    def _review_all(self) -> None:
        """Review every move of an imported game, in order (one engine call at a time)."""
        stack = list(self.board.move_stack)
        board = self.board.root()
        for ply, move in enumerate(stack):
            if self._closed:
                return
            self._run_review(board.copy(stack=False), move, ply)
            board.push(move)
            self._set_state(status=f"Analysing the imported game... {ply + 1}/{len(stack)} moves")
        self._set_state(status="Analysis complete - use Left/Right to step through the moves.")

    def export_pgn_text(self) -> str:
        from ..explain.pgn import export_pgn

        with self._lock:
            reviews = dict(self._reviews)
        if self.analysis_mode:
            return export_pgn(
                self.board,
                reviews,
                white=self.side_name(chess.WHITE),
                black=self.side_name(chess.BLACK),
                event=self.headers.get("Event", "Imported game"),
                extra_headers=self.headers,
            )
        names = {self.human_color: "You", not self.human_color: self.opponent_name}
        return export_pgn(self.board, reviews, white=names[chess.WHITE], black=names[chess.BLACK])

    def reviews_snapshot(self) -> dict[int, MoveReview]:
        with self._lock:
            return dict(self._reviews)

    @property
    def is_human_turn(self) -> bool:
        return (
            not self.analysis_mode
            and self.at_latest
            and self.board.turn == self.human_color
            and not self.board.is_game_over()
            and not self.state.game_over
            and self._lichess_ready()
        )

    @property
    def _opponent_to_move(self) -> bool:
        return self.board.turn != self.human_color and not self.board.is_game_over()

    @property
    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    # -- player moves -------------------------------------------------------- #
    def legal_targets(self, square: chess.Square) -> list[chess.Square]:
        """Destination squares for a legal move from ``square`` (for move dots)."""
        return [m.to_square for m in self.board.legal_moves if m.from_square == square]

    def try_player_move(self, from_sq: chess.Square, to_sq: chess.Square) -> bool:
        """Attempt the player's move; returns ``True`` if it was legal and made.

        Auto-promotes to a queen (the overwhelmingly common choice); the GUI can
        be extended with a promotion picker later.
        """
        if not self.is_human_turn or self.is_busy:
            return False
        move = chess.Move(from_sq, to_sq)
        if move not in self.board.legal_moves:
            promo = chess.Move(from_sq, to_sq, promotion=chess.QUEEN)
            if promo in self.board.legal_moves:
                move = promo
            else:
                return False
        san = self.board.san(move)
        before = self.board.copy(stack=False)
        ply = len(self.board.move_stack)
        self.board.push(move)
        self._schedule_review(before, move, ply)
        if self.board.is_game_over():
            self._set_state(
                status="Game over.",
                headline=f"You played {san}.",
                last_move_uci=move.uci(),
                game_over=True,
                narrative=self._result_text(),
            )
        else:
            self._set_state(
                status=f"{self.opponent_name} is thinking...",
                thinking=True,
                headline=f"You played {san}.",
                last_move_uci=move.uci(),
            )
        if self._lichess is not None:
            # Forward the move right away (and then wait for the bot's reply) on
            # the worker -- even a game-ending move must reach Lichess.
            self._start_worker(self._run_lichess_turn)
        return True

    # -- tutor moves (background) ------------------------------------------- #
    @property
    def should_start_tutor_turn(self) -> bool:
        """Whether the tutor's move may be scheduled right now.

        This is the pure, pygame-free scheduling predicate used by the render
        loop. It is deliberately *not* gated on ``state.thinking``: a player move
        marks the state ``thinking`` before any worker thread exists, so gating on
        it would stop the tutor turn from ever starting. ``is_busy`` (a live
        worker thread) is the correct "already working" guard.
        """
        return not (
            self.analysis_mode
            or self.state.game_over
            or not self._opponent_to_move
            or self.is_busy
            or self._closed
        )

    def start_tutor_turn(self) -> None:
        """Kick off the tutor's move on a worker thread if it is its turn."""
        if not self.should_start_tutor_turn:
            return
        self._set_state(status=f"{self.opponent_name} is thinking...", thinking=True)
        target = self._run_lichess_turn if self._lichess is not None else self._run_tutor_turn
        self._start_worker(target)

    def _start_worker(self, target) -> None:
        self._worker = threading.Thread(target=target, daemon=True)
        self._worker.start()

    def _run_tutor_turn(self) -> None:
        fen = self.board.fen()
        try:
            decision = self._engine.select_move(fen)
        except (AnalysisError, LLMError) as exc:  # surface, don't crash the UI thread
            self._set_state(status="Engine error.", thinking=False, narrative=str(exc))
            return
        self._apply_tutor_decision(decision)

    def _apply_tutor_decision(self, decision: MoveDecision) -> None:
        move = chess.Move.from_uci(decision.move_uci)
        san = self.board.san(move) if move in self.board.legal_moves else decision.move_uci
        rows = tuple(
            comparison_rows(
                decision.analysis, proposal=decision.proposal, chosen_uci=decision.move_uci
            )
        )
        narrative = why_this_move(decision)
        eval_cp, eval_mate = _white_perspective_eval(decision.analysis)
        self._store_analysis(decision.analysis)
        before = self.board.copy(stack=False)
        ply = len(self.board.move_stack)
        self.board.push(move)
        self._schedule_review(before, move, ply)
        over = self.board.is_game_over()
        self._set_state(
            status="Your move." if not over else "Game over.",
            thinking=False,
            headline=f"Tutor played {san} {self._tag(decision.source)}",
            narrative=(self._result_text() if over else narrative),
            rows=rows,
            last_move_uci=decision.move_uci,
            game_over=over,
            eval_cp=eval_cp,
            eval_mate=eval_mate,
        )

    # -- Lichess opponent (background) ---------------------------------------- #
    def _run_lichess_turn(self) -> None:
        """Send our unsent move (if any) to Lichess, then wait for the bot's reply."""
        game = self._lichess
        if game is None:
            return
        try:
            snap = game.snapshot()
            if len(self.board.move_stack) > len(snap.moves) and snap.game_id:
                game.send_move(self.board.move_stack[-1].uci())
        except LichessError as exc:
            # Lichess refused the move: take it back locally so both boards agree.
            snap = game.snapshot()
            while len(self.board.move_stack) > len(snap.moves):
                self.board.pop()
            self._set_state(
                status="Lichess rejected the move - try again.",
                thinking=False,
                game_over=False,
                narrative=str(exc),
                last_move_uci=None,
            )
            return
        if self.board.is_game_over():
            return  # our move ended the game; the local result is already shown

        target = len(self.board.move_stack) + 1
        while not (self._closed or game.stopped):
            snap = game.wait_for_move_count(target, timeout=1.0)
            if len(snap.moves) >= target:
                self._apply_lichess_moves(snap)
                return
            if snap.is_over:
                self._finish_from_lichess(snap)
                return

    def _apply_lichess_moves(self, snap: GameSnapshot) -> None:
        """Push moves Lichess has that the local board doesn't (the bot's reply)."""
        if self._closed:
            return
        last_san, last_uci = "", None
        for uci in snap.moves[len(self.board.move_stack) :]:
            move = chess.Move.from_uci(uci)
            if move not in self.board.legal_moves:
                self._set_state(
                    status="Board out of sync with Lichess.",
                    thinking=False,
                    narrative=f"Lichess sent {uci}, which is illegal here. Press N.",
                )
                return
            last_san, last_uci = self.board.san(move), uci
            before = self.board.copy(stack=False)
            ply = len(self.board.move_stack)
            self.board.push(move)
            self._schedule_review(before, move, ply)
        over = self.board.is_game_over() or snap.is_over
        self._set_state(
            status="Game over." if over else "Your move.",
            thinking=False,
            headline=f"{self.opponent_name} played {last_san}." if last_san else "",
            last_move_uci=last_uci,
            game_over=over,
            narrative=self._end_text(snap) if over else "",
            rows=(),
        )

    def _finish_from_lichess(self, snap: GameSnapshot) -> None:
        if self._closed:
            return
        self._set_state(
            status="Game over." if snap.status not in ("declined", "error") else "Lichess problem.",
            thinking=False,
            game_over=True,
            narrative=self._end_text(snap),
        )

    def _end_text(self, snap: GameSnapshot) -> str:
        if snap.is_over and self._lichess is not None:
            return describe_end(snap, bot=self._lichess.bot, human_color=self.human_color)
        return self._result_text()

    def poll_lichess(self) -> None:
        """Per-frame sync with Lichess (connect status, resign/timeout/abort).

        Moves are applied by the worker; this only handles events that can happen
        while no worker runs (game start, the bot resigning, our flag falling...).
        """
        if self._lichess is None or self._closed or self.state.game_over or self.is_busy:
            return
        snap = self._lichess.snapshot()
        if snap.is_over:
            if len(snap.moves) > len(self.board.move_stack):
                self._apply_lichess_moves(snap)
            if not self.state.game_over:
                self._finish_from_lichess(snap)
            return
        if not snap.game_id and snap.message and self.state.status.startswith("Connecting"):
            status = f"Connecting to Lichess ({self._lichess.bot})... {snap.message}"
            if self.state.status != status:
                self._set_state(status=status)
        if snap.game_id and self.state.status.startswith("Connecting"):
            if self.board.turn == self.human_color:
                self._set_state(status="Your move.")
            else:
                self._set_state(status=f"{self.opponent_name} to move.")

    def clock_texts(self, now: float | None = None) -> tuple[str, str] | None:
        """``(your_clock, opponent_clock)`` as ``mm:ss``, or ``None`` when local."""
        snap = self.lichess_snapshot
        if snap is None:
            return None
        w, b = live_clocks(snap, time.monotonic() if now is None else now)
        if self.human_color == chess.WHITE:
            return format_clock(w), format_clock(b)
        return format_clock(b), format_clock(w)

    def close(self, *, wait: bool = True) -> None:
        """Leave the Lichess game (abort/resign). Background if ``wait`` is False."""
        self._closed = True
        game = self._lichess
        if game is None:
            return
        if wait:
            game.stop()
        else:
            threading.Thread(target=game.stop, daemon=True).start()

    # -- proactive coaching for the side to move (background) ---------------- #
    @property
    def should_coach_side_to_move(self) -> bool:
        """Whether to proactively coach the player about the current position.

        Fires at most once per position and only on the **human's** turn -- the
        tutor's own moves are already explained by :meth:`_apply_tutor_decision`,
        so between the two, coaching is produced for *both* sides to move.

        Like :attr:`should_start_tutor_turn` this is a pure, pygame-free predicate
        so the scheduling can be unit-tested. Crucially it uses a *separate*
        worker from ``is_busy``, so the player is never blocked from moving while
        the coach is still thinking about the position.
        """
        if self.board.is_game_over() or self.state.game_over:
            return False
        if not self.is_human_turn:
            return False
        if self._coach_worker is not None and self._coach_worker.is_alive():
            return False
        return self._coached_fen != self.board.fen()

    def coach_side_to_move(self) -> None:
        """Kick off coaching for the player's position on the coach worker."""
        if not self.should_coach_side_to_move:
            return
        fen = self.board.fen()
        self._coached_fen = fen
        self._set_state(status="Coaching your move...", thinking=True)
        self._coach_worker = threading.Thread(
            target=self._run_coach_side_to_move, args=(fen,), daemon=True
        )
        self._coach_worker.start()

    def _run_coach_side_to_move(self, fen: str) -> None:
        # Deterministic coaching (no LLM): one free engine analysis + board facts.
        try:
            analysis = self._analyse(fen)
        except (AnalysisError, LLMError):
            # Coaching is best-effort: a failed analysis must not disturb play nor
            # clobber the existing panel. Clear only the transient thinking flag.
            if self.board.fen() == fen:
                self._set_state(status="Your move.", thinking=False)
            return
        # Stale guard: if the player has already moved on, drop the result.
        if self.board.fen() != fen:
            return
        coaching = coach_position(chess.Board(fen), analysis)
        if self.board.fen() != fen:
            return
        eval_cp, eval_mate = _white_perspective_eval(analysis)
        self._set_state(
            status="Your move.",
            thinking=False,
            rows=tuple(comparison_rows(analysis)),
            eval_cp=eval_cp,
            eval_mate=eval_mate,
            coaching=coaching,
            coaching_fen=fen,
        )

    # -- move reviews (every move, both sides; background) -------------------- #
    def _schedule_review(self, before: chess.Board, move: chess.Move, ply: int) -> None:
        threading.Thread(
            target=self._run_review, args=(before, move, ply), daemon=True
        ).start()

    def _run_review(self, before: chess.Board, move: chess.Move, ply: int) -> None:
        if self._engine is None:
            return
        after = before.copy(stack=False)
        after.push(move)
        a_before: Analysis | None
        a_after: Analysis | None
        try:
            a_before = self._analyse(before.fen())
        except Exception:  # noqa: BLE001 - reviews degrade to board facts only
            a_before = None
        try:
            a_after = None if after.is_game_over() else self._analyse(after.fen())
        except Exception:  # noqa: BLE001
            a_after = None
        if self._closed:
            return
        try:
            review = review_move(before, move, a_before, a_after, ply=ply)
        except Exception as exc:  # noqa: BLE001 - an explanation bug must not kill play
            self._set_state(narrative=f"(Could not explain {move.uci()}: {exc})")
            return
        with self._lock:
            # Ignore reviews for a different game line (e.g. a rejected move).
            if len(self.board.move_stack) <= ply or self.board.move_stack[ply] != move:
                return
            self._reviews[ply] = review
            latest = sorted(self._reviews)[-2:]
            self._state = replace(
                self._state, reviews=tuple(self._reviews[p] for p in latest)
            )

    def review_for(self, ply: int) -> MoveReview | None:
        with self._lock:
            return self._reviews.get(ply)

    # -- on-demand chat (LLM, grounded in computed facts) --------------------- #
    def ask_chat(self, question: str) -> None:
        """Ask the LLM about the current position on a background thread."""
        question = question.strip()
        if not question or self.chat_client is None or self.state.chat_busy:
            return
        fen = self.view_board.fen()
        v = self.view_len
        self._chat_reviews = tuple(
            r for r in (self.review_for(v - 2), self.review_for(v - 1)) if r is not None
        )
        history = list(self.state.chat) if self.state.chat_fen == fen else []
        self._set_state(chat=(*history, ("user", question)), chat_fen=fen, chat_busy=True, chat_marks=())
        threading.Thread(
            target=self._run_chat, args=(fen, history, question), daemon=True
        ).start()

    def _run_chat(self, fen: str, history: list[tuple[str, str]], question: str) -> None:
        board = chess.Board(fen)
        try:
            analysis = self._analyse(fen) if self._engine is not None else None
        except Exception:  # noqa: BLE001 - chat still works from board facts
            analysis = None
        state = self.state
        coaching = state.coaching if state.coaching_fen == fen else None
        reviews = getattr(self, "_chat_reviews", state.reviews)
        context = build_context(board, analysis, reviews, coaching, self.human_color)
        try:
            answer = self.chat_client.ask(context, history, question)  # type: ignore[union-attr]
            marks = cited_squares(answer, context)
        except ChatError as exc:
            answer, marks = f"(Chat failed: {exc})", ()
        if self.state.chat_fen != fen:
            self._set_state(chat_busy=False)
            return
        # If the player has moved meanwhile, the GUI hides this (chat_fen != board).
        self._set_state(
            chat=(*self.state.chat, ("assistant", answer)), chat_busy=False, chat_marks=marks
        )

    # -- shared analysis cache ------------------------------------------------ #
    def _store_analysis(self, analysis: Analysis) -> None:
        with self._analysis_lock:
            self._analyses[analysis.fen] = analysis

    def _analyse(self, fen: str) -> Analysis:
        """Engine analysis of ``fen``, computed once and shared between threads."""
        while True:
            with self._analysis_lock:
                cached = self._analyses.get(fen)
                if cached is not None:
                    return cached
                event = self._inflight.get(fen)
                if event is None:
                    event = threading.Event()
                    self._inflight[fen] = event
                    owner = True
                else:
                    owner = False
            if not owner:
                event.wait(timeout=60)
                with self._analysis_lock:
                    if fen in self._analyses:
                        return self._analyses[fen]
                    if fen in self._inflight:
                        continue
                # The owner failed; try ourselves.
                continue
            try:
                analysis = self._engine.analyse(fen)
                with self._analysis_lock:
                    self._analyses[fen] = analysis
                return analysis
            finally:
                with self._analysis_lock:
                    self._inflight.pop(fen, None)
                event.set()

    # -- coaching queries ---------------------------------------------------- #
    def explain_why_not(self, from_sq: chess.Square, to_sq: chess.Square) -> None:
        """Explain why a selected alternative is not the engine's pick.

        Uses **only the free chess-api analysis** -- no LLM call -- so the player
        can explore "why not X?" freely without incurring token cost. The engine
        analysis of the current position is cached, so repeated questions about the
        same position don't even re-hit the (free) chess-api.
        """
        if self.is_busy or not self.is_human_turn:
            return
        move_uci = chess.Move(from_sq, to_sq).uci()
        self._set_state(status="Analysing...", thinking=True)
        self._worker = threading.Thread(
            target=self._run_why_not, args=(move_uci,), daemon=True
        )
        self._worker.start()

    def _run_why_not(self, move_uci: str) -> None:
        board = self.board.copy(stack=False)
        fen = board.fen()
        move = chess.Move.from_uci(move_uci)
        if move not in board.legal_moves:
            move = chess.Move(move.from_square, move.to_square, promotion=chess.QUEEN)
        try:
            analysis = self._analyse(fen)
            after = board.copy(stack=False)
            after.push(move)
            a_after = None if after.is_game_over() else self._analyse(after.fen())
        except (AnalysisError, LLMError) as exc:
            self._set_state(status="Engine error.", thinking=False, narrative=str(exc))
            return
        # Free engine analysis + board facts: a full review of the hypothetical move.
        review = review_move(board, move, analysis, a_after, ply=len(self.board.move_stack))
        parts = [f"{review.title} - {review.eval_text}."]
        parts += list(review.points)
        if review.problem:
            parts.append(review.problem)
        if review.better:
            parts.append(review.better)
        if review.label in ("Best", "Excellent", "Good"):
            parts.append(why_not_move(analysis, move.uci()))
        eval_cp, eval_mate = _white_perspective_eval(analysis)
        self._set_state(
            status="Your move.",
            thinking=False,
            headline=f"What if {review.san}?",
            narrative="\n".join(parts),
            rows=tuple(comparison_rows(analysis)),
            eval_cp=eval_cp,
            eval_mate=eval_mate,
        )

    # -- helpers ------------------------------------------------------------- #
    @staticmethod
    def _tag(source: str) -> str:
        return {
            "llm": "[coach]",
            "engine-veto": "[engine veto]",
            "engine-fallback": "[engine fallback]",
            "engine-only": "[engine only]",
        }.get(source, f"[{source}]")

    def _result_text(self) -> str:
        outcome = self.board.outcome()
        if outcome is None:
            return ""
        if outcome.winner is None:
            return f"Draw ({outcome.termination.name.replace('_', ' ').title()})."
        winner = "White" if outcome.winner == chess.WHITE else "Black"
        return f"{winner} wins ({outcome.termination.name.replace('_', ' ').title()})."
