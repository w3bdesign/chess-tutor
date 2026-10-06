"""Pygame desktop front-end for the hybrid chess tutor.

This is a *thin consumer* of the shared engine core. It owns no chess rules and no
move-selection logic of its own: python-chess validates moves and
:class:`~chess_tutor.gui.controller.GameController` drives the authoritative
:class:`~chess_tutor.engine.hybrid.HybridEngine` on a background thread so the
window never freezes during a chess-api.com or LLM call.

Controls
--------
* Click a piece, then click a destination to move (auto-queens on promotion).
* Right-click a legal destination of the selected piece to ask, for free,
  "why not that move?" (engine-only analysis -- no LLM cost).
* ``f`` flips the board; ``n`` starts a new game; ``Esc`` clears the selection.

Run with ``chess-tutor-gui`` (after ``uv pip install -e ".[gui]"``) or
``python -m chess_tutor.gui.app``.
"""

from __future__ import annotations

import sys

import chess
import pygame

from ..config import load_settings
from ..engine.chess_api import ChessApiProvider
from ..engine.hybrid import HybridEngine
from .controller import GameController
from .geometry import BoardLayout
from .pieces import PieceRenderer, load_glyph_font
from .theme import DEFAULT_THEME, Theme

_FPS = 60
_TUTOR_MOVE_DELAY_MS = 350  # small pause so the player sees their move land


class ChessTutorApp:
    """Owns the pygame window, the render loop, and user input handling."""

    def __init__(
        self,
        controller: GameController,
        *,
        theme: Theme = DEFAULT_THEME,
    ) -> None:
        self.controller = controller
        self.theme = theme
        self.perspective = controller.human_color
        self.layout = BoardLayout(theme, perspective=self.perspective)
        self.pieces = PieceRenderer(theme)
        self.screen = pygame.display.set_mode((theme.window_width, theme.window_height))
        pygame.display.set_caption("Chess Tutor")
        self.clock = pygame.time.Clock()
        self._label_font = pygame.font.SysFont(None, 20)
        self._panel_font = pygame.font.SysFont(None, 22)
        self._heading_font = pygame.font.SysFont(None, 26, bold=True)
        self._small_font = pygame.font.SysFont(None, 18)
        # A Unicode-glyph-capable font so captured-piece symbols render as pieces
        # instead of missing-glyph boxes (the default SysFont lacks them).
        self._glyph_font = load_glyph_font(20)
        self._mono_font = pygame.font.SysFont("consolas,couriernew,monospace", 16)

        self.selected: chess.Square | None = None
        self.legal_targets: list[chess.Square] = []
        self._tutor_scheduled_at: int | None = None

    # -- main loop ----------------------------------------------------------- #
    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    self._on_key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._on_click(event.pos, event.button)

            self._maybe_start_tutor_turn()
            self.controller.coach_side_to_move()
            self._draw()
            pygame.display.flip()
            self.clock.tick(_FPS)

        self.controller._engine.close()
        pygame.quit()

    # -- scheduling the tutor ------------------------------------------------ #
    def _maybe_start_tutor_turn(self) -> None:
        """Start the tutor's (threaded) move shortly after it becomes its turn.

        The scheduling decision itself lives in the pygame-free
        :attr:`GameController.should_start_tutor_turn` predicate (unit-tested);
        this method only owns the small presentation delay.
        """
        if not self.controller.should_start_tutor_turn:
            self._tutor_scheduled_at = None
            return
        now = pygame.time.get_ticks()
        if self._tutor_scheduled_at is None:
            self._tutor_scheduled_at = now + _TUTOR_MOVE_DELAY_MS
        elif now >= self._tutor_scheduled_at:
            self._tutor_scheduled_at = None
            self.controller.start_tutor_turn()

    # -- input --------------------------------------------------------------- #
    def _on_key(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            self._clear_selection()
        elif key == pygame.K_f:
            self._flip_board()
        elif key == pygame.K_n:
            self._new_game()

    def _on_click(self, pos: tuple[int, int], button: int) -> None:
        if self.controller.is_busy or not self.controller.is_human_turn:
            return
        square = self.layout.square_at(*pos)
        if square is None:
            self._clear_selection()
            return

        # Right-click a candidate target -> free "why not?" explanation.
        if button == 3 and self.selected is not None and square in self.legal_targets:
            self.controller.explain_why_not(self.selected, square)
            return
        if button != 1:
            return

        if self.selected is None:
            self._select(square)
            return

        if square == self.selected:
            self._clear_selection()
            return

        if square in self.legal_targets:
            if self.controller.try_player_move(self.selected, square):
                self._clear_selection()
            return

        # Clicking another of your own pieces reselects it.
        self._select(square)

    def _select(self, square: chess.Square) -> None:
        piece = self.controller.board.piece_at(square)
        if piece is not None and piece.color == self.controller.human_color:
            self.selected = square
            self.legal_targets = self.controller.legal_targets(square)
        else:
            self._clear_selection()

    def _clear_selection(self) -> None:
        self.selected = None
        self.legal_targets = []

    def _flip_board(self) -> None:
        self.perspective = not self.perspective
        self.layout = BoardLayout(self.theme, perspective=self.perspective)

    def _new_game(self) -> None:
        human = self.controller.human_color
        engine = self.controller._engine
        self.controller = GameController(engine, human_color=human)
        self._clear_selection()
        self._tutor_scheduled_at = None

    # -- rendering ----------------------------------------------------------- #
    def _draw(self) -> None:
        self.screen.fill(self.theme.background)
        state = self.controller.state
        self._draw_board(state)
        self._draw_pieces()
        self._draw_labels()
        self._draw_panel(state)

    def _draw_board(self, state) -> None:
        last_move = self._last_move_squares(state)
        check_sq = self._king_in_check_square()
        for square in chess.SQUARES:
            rect = self.layout.square_rect(square)
            light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
            colour = self.theme.light_square if light else self.theme.dark_square
            pygame.draw.rect(self.screen, colour, (rect.x, rect.y, rect.width, rect.height))
            if square in last_move:
                self._tint(rect, self.theme.last_move)
            if square == self.selected:
                self._tint(rect, self.theme.selected)
            if square == check_sq:
                self._tint(rect, self.theme.check)
        self._draw_move_hints()

    def _draw_move_hints(self) -> None:
        board = self.controller.board
        for target in self.legal_targets:
            rect = self.layout.square_rect(target)
            cx, cy = rect.center
            if board.piece_at(target) is not None:
                # Capture: draw a ring around the occupied square.
                pygame.draw.circle(
                    self.screen, self.theme.legal_ring, (cx, cy), rect.width // 2 - 3, 4
                )
            else:
                dot = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                pygame.draw.circle(
                    dot,
                    (*self.theme.legal_dot, 90),
                    (rect.width // 2, rect.height // 2),
                    rect.width // 6,
                )
                self.screen.blit(dot, (rect.x, rect.y))

    def _draw_pieces(self) -> None:
        board = self.controller.board
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece is None:
                continue
            rect = self.layout.square_rect(square)
            self.pieces.blit_centered(self.screen, piece, rect.center)

    def _draw_labels(self) -> None:
        for letter, x, y in self.layout.file_label_positions():
            surf = self._label_font.render(letter, True, self.theme.label)
            self.screen.blit(surf, surf.get_rect(center=(x, y + 8)))
        for digit, x, y in self.layout.rank_label_positions():
            surf = self._label_font.render(digit, True, self.theme.label)
            self.screen.blit(surf, surf.get_rect(center=(x, y)))

    def _draw_panel(self, state) -> None:
        panel = self.layout.panel_rect
        pygame.draw.rect(
            self.screen, self.theme.panel_bg, (panel.x, panel.y, panel.width, panel.height)
        )
        pad = 16
        x = panel.x + pad
        y = pad

        # Status line.
        status_colour = (
            self.theme.status_thinking if state.thinking else self.theme.panel_text
        )
        y = self._blit_text(state.status, self._heading_font, status_colour, x, y, panel)
        y += 6

        if state.headline:
            y = self._blit_text(state.headline, self._panel_font, self.theme.panel_heading, x, y, panel)
            y += 4

        # Captured material summary.
        y = self._draw_captured(x, y, panel)
        y += 8

        # Comparison table.
        if state.rows:
            y = self._blit_text("Candidates", self._panel_font, self.theme.panel_heading, x, y, panel)
            y = self._draw_rows(state.rows, x, y, panel)
            y += 6

        # Narrative (wrapped).
        if state.narrative:
            y = self._blit_text("Coach", self._panel_font, self.theme.panel_heading, x, y, panel)
            y = self._blit_wrapped(state.narrative, self._small_font, self.theme.panel_text, x, y, panel)

        # Controls hint pinned near the bottom.
        hint = "L-click: move   R-click: why not?   F: flip   N: new   Esc: clear"
        hint_surf = self._small_font.render(hint, True, self.theme.panel_muted)
        self.screen.blit(hint_surf, (x, panel.height - 24))

    def _draw_rows(self, rows, x: int, y: int, panel) -> int:
        for row in rows[:6]:
            marker = "*" if row.is_chosen else ("=" if row.is_best else " ")
            loss = "" if row.loss_cp == 0 else f"  -{row.loss_cp}cp"
            text = f"{marker} {row.rank}. {row.move:<7} {row.score}{loss}"
            highlighted = row.is_chosen or row.is_best
            colour = (
                self.theme.panel_heading
                if row.is_chosen
                else (self.theme.panel_text if row.is_best else self.theme.panel_muted)
            )
            surf = self._small_font.render(text, True, colour)
            self.screen.blit(surf, (x, y))
            y += surf.get_height() + 2
            # Show the replayable SAN variation behind the headline line(s) so the
            # learner can follow it on a board. Only for the best/chosen line to
            # keep the panel readable.
            variation = row.pv_san or row.pv
            if highlighted and variation:
                y = self._blit_wrapped(
                    f"   {variation}", self._small_font, self.theme.panel_muted, x, y, panel
                )
        return y

    def _draw_captured(self, x: int, y: int, panel) -> int:
        white_cap, black_cap = self._captured_pieces()
        line = f"You: {''.join(white_cap) or '-'}   Tutor: {''.join(black_cap) or '-'}"
        return self._blit_text(line, self._small_font, self.theme.panel_muted, x, y, panel)

    # -- small drawing helpers ---------------------------------------------- #
    def _tint(self, rect, colour: tuple[int, int, int]) -> None:
        overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        overlay.fill((*colour, self.theme.overlay_alpha))
        self.screen.blit(overlay, (rect.x, rect.y))

    def _blit_text(self, text, font, colour, x: int, y: int, panel) -> int:
        surf = font.render(text, True, colour)
        self.screen.blit(surf, (x, y))
        return y + surf.get_height() + 2

    def _blit_wrapped(self, text, font, colour, x: int, y: int, panel) -> int:
        max_width = panel.width - 32
        for line in _wrap(text, font, max_width):
            surf = font.render(line, True, colour)
            self.screen.blit(surf, (x, y))
            y += surf.get_height() + 2
        return y

    # -- board state introspection ------------------------------------------ #
    def _last_move_squares(self, state) -> set[chess.Square]:
        if not state.last_move_uci:
            return set()
        try:
            move = chess.Move.from_uci(state.last_move_uci)
        except ValueError:
            return set()
        return {move.from_square, move.to_square}

    def _king_in_check_square(self) -> chess.Square | None:
        board = self.controller.board
        if not board.is_check():
            return None
        return board.king(board.turn)

    def _captured_pieces(self) -> tuple[list[str], list[str]]:
        """Glyphs for pieces captured by White (you) and Black (tutor)."""
        board = self.controller.board
        start = {
            chess.PAWN: 8,
            chess.KNIGHT: 2,
            chess.BISHOP: 2,
            chess.ROOK: 2,
            chess.QUEEN: 1,
        }
        glyphs = {
            chess.PAWN: "♟",
            chess.KNIGHT: "♞",
            chess.BISHOP: "♝",
            chess.ROOK: "♜",
            chess.QUEEN: "♛",
        }
        captured_by_white: list[str] = []
        captured_by_black: list[str] = []
        for ptype, count in start.items():
            white_left = len(board.pieces(ptype, chess.WHITE))
            black_left = len(board.pieces(ptype, chess.BLACK))
            captured_by_white += glyphs[ptype] * (count - black_left)
            captured_by_black += glyphs[ptype] * (count - white_left)
        return captured_by_white, captured_by_black


def _wrap(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Greedy word-wrap ``text`` to ``max_width`` pixels for ``font``."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if font.size(trial)[0] <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        lines.append(current)
    return lines


def _build_engine() -> HybridEngine:
    """Construct the hybrid engine from environment settings (same as the CLI)."""
    settings = load_settings()
    provider = ChessApiProvider(settings.chess_api_ws_url)
    return HybridEngine.from_settings(settings, provider)


def main() -> None:
    """Entry point for the ``chess-tutor-gui`` script."""
    pygame.init()
    try:
        engine = _build_engine()
        controller = GameController(engine, human_color=chess.WHITE)
        app = ChessTutorApp(controller)
        app.run()
    finally:
        if pygame.get_init():
            pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
