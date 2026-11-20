"""Temporary: import a real PGN through the GUI controller, review it with the real
engine, browse, export the annotated PGN. Renders one frame headlessly."""

import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import chess  # noqa: E402
import pygame  # noqa: E402

from chess_tutor.config import load_settings  # noqa: E402
from chess_tutor.explain.pgn import load_pgn  # noqa: E402
from chess_tutor.gui.app import ChessTutorApp, _build_engine  # noqa: E402
from chess_tutor.gui.controller import GameController  # noqa: E402

PGN = """[Event "Paris Opera"]
[White "Paul Morphy"]
[Black "Duke Karl / Count Isouard"]
[Result "1-0"]

1. e4 e5 2. Nf3 d6 3. d4 Bg4 4. dxe5 Bxf3 5. Qxf3 dxe5 6. Bc4 Nf6 7. Qb3 Qe7
8. Nc3 c6 9. Bg5 b5 10. Nxb5 cxb5 11. Bxb5+ Nbd7 12. O-O-O Rd8 13. Rxd7 Rxd7
14. Rd1 Qe6 15. Bxd7+ Nxd7 16. Qb8+ Nxb8 17. Rd8# 1-0
"""

pygame.init()
board, headers = load_pgn(PGN)
ctrl = GameController(_build_engine(load_settings()), human_color=chess.WHITE, board=board,
                      analysis_headers=headers)
app = ChessTutorApp(ctrl)
t0 = time.time()
while time.time() - t0 < 240 and not ctrl.state.status.startswith("Analysis complete"):
    time.sleep(1)
print(ctrl.state.status, f"({time.time() - t0:.0f}s)")
ctrl.set_view(7)  # after 4.dxe5
app._draw()
pygame.image.save(app.screen, "render_pgn.png")
print("view 7:", ctrl.view_board.fen(), "| review:", ctrl.review_for(6).title)
text = ctrl.export_pgn_text()
print(text[:1500])
pygame.quit()
