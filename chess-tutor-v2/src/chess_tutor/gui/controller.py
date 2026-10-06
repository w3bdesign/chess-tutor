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
from dataclasses import dataclass, replace

import chess

from ..engine.hybrid import HybridEngine, MoveDecision
from ..engine.llm import LLMError
from ..engine.models import Analysis
from ..engine.provider import AnalysisError
from ..engine.teaching import ComparisonRow, comparison_rows, why_not_move, why_this_move


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


class GameController:
    """Owns the board, the engine, and the background worker for tutor moves."""

    def __init__(
        self,
        engine: HybridEngine,
        *,
        human_color: chess.Color = chess.WHITE,
        board: chess.Board | None = None,
    ) -> None:
        self._engine = engine
        self.human_color = human_color
        self.board = board if board is not None else chess.Board()
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
        # Cache of the latest free engine analysis, keyed by FEN, so repeated
        # "why not?" questions about the same position cost nothing.
        self._analysis_cache: tuple[str, Analysis] | None = None

    # -- state access -------------------------------------------------------- #
    def _initial_status(self) -> str:
        return "Your move." if self.human_color == chess.WHITE else "Tutor to move."

    @property
    def state(self) -> CoachState:
        with self._lock:
            return self._state

    def _set_state(self, **changes: object) -> None:
        with self._lock:
            self._state = replace(self._state, **changes)

    @property
    def is_human_turn(self) -> bool:
        return self.board.turn == self.human_color and not self.board.is_game_over()

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
        self.board.push(move)
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
                status="Tutor is thinking...",
                thinking=True,
                headline=f"You played {san}.",
                last_move_uci=move.uci(),
            )
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
            self.state.game_over
            or self.is_human_turn
            or self.is_busy
            or self.board.is_game_over()
        )

    def start_tutor_turn(self) -> None:
        """Kick off the tutor's move on a worker thread if it is its turn."""
        if self.is_busy or self.is_human_turn or self.board.is_game_over():
            return
        self._set_state(status="Tutor is thinking...", thinking=True)
        self._worker = threading.Thread(target=self._run_tutor_turn, daemon=True)
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
        self.board.push(move)
        over = self.board.is_game_over()
        self._set_state(
            status="Your move." if not over else "Game over.",
            thinking=False,
            headline=f"Tutor played {san} {self._tag(decision.source)}",
            narrative=(self._result_text() if over else narrative),
            rows=rows,
            last_move_uci=decision.move_uci,
            game_over=over,
        )

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
        try:
            decision = self._engine.select_move(fen)
        except (AnalysisError, LLMError):
            # Coaching is best-effort: a failed analysis must not disturb play nor
            # clobber the existing panel. Clear only the transient thinking flag.
            if self.board.fen() == fen:
                self._set_state(status="Your move.", thinking=False)
            return
        # Stale guard: if the player has already moved on, drop the result.
        if self.board.fen() != fen:
            return
        self._publish_coaching(decision)

    def _publish_coaching(self, decision: MoveDecision) -> None:
        """Publish side-to-move coaching (best move + why + candidate rows)."""
        board = chess.Board(decision.analysis.fen)
        move = chess.Move.from_uci(decision.move_uci)
        san = board.san(move) if move in board.legal_moves else decision.move_uci
        rows = tuple(
            comparison_rows(
                decision.analysis, proposal=decision.proposal, chosen_uci=decision.move_uci
            )
        )
        self._set_state(
            status="Your move.",
            thinking=False,
            headline=f"Your best: {san} {self._tag(decision.source)}",
            narrative=why_this_move(decision),
            rows=rows,
        )

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
        try:
            analysis = self._analysis_for_current_position()
        except (AnalysisError, LLMError) as exc:
            self._set_state(status="Engine error.", thinking=False, narrative=str(exc))
            return
        # Deliberately no LLM proposal here: why-not explanations are derived from
        # the free engine analysis to keep exploration cost-free.
        text = why_not_move(analysis, move_uci)
        rows = tuple(comparison_rows(analysis))
        self._set_state(
            status="Your move.",
            thinking=False,
            headline=f"Why not {move_uci}?",
            narrative=text,
            rows=rows,
        )

    def _analysis_for_current_position(self) -> Analysis:
        """Return a cached (free) engine analysis for the current position."""
        fen = self.board.fen()
        if self._analysis_cache is not None and self._analysis_cache[0] == fen:
            return self._analysis_cache[1]
        analysis = self._engine.analyse(fen)
        self._analysis_cache = (fen, analysis)
        return analysis

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
