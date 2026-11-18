"""Headless render check: play a few moves with a fake engine, render every tab to PNG.

Usage: .venv\\Scripts\\python.exe scripts/gui_render_check.py
Writes render_tab1.png / render_tab2.png / render_tab3.png in the project root.
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import chess  # noqa: E402
import pygame  # noqa: E402

from chess_tutor.engine.models import Analysis, CandidateLine  # noqa: E402
from chess_tutor.gui.app import ChessTutorApp  # noqa: E402
from chess_tutor.gui.controller import GameController  # noqa: E402


class FakeEngine:
    """Scores every legal move by material after it (crude, but deterministic)."""

    def analyse(self, fen: str) -> Analysis:
        board = chess.Board(fen)
        lines = []
        for move in list(board.legal_moves)[:40]:
            b = board.copy()
            b.push(move)
            score = sum(
                (1 if p.color == board.turn else -1)
                * {1: 100, 2: 300, 3: 300, 4: 500, 5: 900, 6: 0}[p.piece_type]
                for p in b.piece_map().values()
            )
            reply = next(iter(b.legal_moves), None)
            pv = [move.uci()] + ([reply.uci()] if reply else [])
            lines.append(CandidateLine(move_uci=move.uci(), move_san=board.san(move), score_cp=score, pv=pv))
        lines.sort(key=lambda c: c.score_cp or 0, reverse=True)
        return Analysis(fen=fen, candidates=[
            CandidateLine(c.move_uci, c.move_san, c.score_cp, None, c.pv, i + 1) for i, c in enumerate(lines[:5])
        ])

    def select_move(self, fen, *, analysis=None):  # pragma: no cover
        raise AssertionError("not used in this check")

    def close(self) -> None:
        pass


def main() -> None:
    pygame.init()
    ctrl = GameController(FakeEngine(), human_color=chess.WHITE)  # type: ignore[arg-type]
    app = ChessTutorApp(ctrl)
    # Ruy Lopez exchange-ish moves, pushed through the controller's review path.
    for uci in ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5c6", "d7c6"]:
        before = ctrl.board.copy(stack=False)
        move = chess.Move.from_uci(uci)
        ply = len(ctrl.board.move_stack)
        ctrl.board.push(move)
        ctrl._schedule_review(before, move, ply)
    ctrl.coach_side_to_move()
    time.sleep(1.5)
    app.show_hint = True
    for tab in range(3):
        app.tab = tab
        app._draw()
        pygame.image.save(app.screen, f"render_tab{tab + 1}.png")
    # Simulate maximizing the window.
    pygame.display.set_mode((1600, 900), pygame.RESIZABLE)
    app._relayout(1600, 900)
    app.tab = 0
    app._draw()
    pygame.image.save(app.screen, "render_maximized.png")
    print("maximized: square", app.theme.square_size, "panel", app.theme.panel_width)
    state = ctrl.state
    print("reviews:", [r.title for r in state.reviews])
    for r in state.reviews:
        print(" ", r.points, "|", r.problem, "|", r.better)
    print("coaching:", state.coaching and state.coaching.plans)
    pygame.quit()


if __name__ == "__main__":
    main()
