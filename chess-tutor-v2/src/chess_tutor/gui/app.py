"""Pygame desktop front-end for the chess tutor.

A thin consumer of the shared core: python-chess validates moves,
:class:`~chess_tutor.gui.controller.GameController` runs the engine / Lichess on
background threads, and the deterministic explain layer
(:mod:`chess_tutor.explain`) produces every explanation shown here.

Design rule for the panel: **one thing at a time, details on demand**. The Review
tab shows a single move card with only the key lines; ``D`` expands everything.
The AI chat lives in its own tab. Press ``?`` (or F1) for all keys.

Run with ``python -m chess_tutor.gui.app`` (see README).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import replace

import chess
import pygame

from ..config import Settings, load_settings
from ..engine.chess_api import ChessApiProvider
from ..engine.hybrid import HybridEngine
from ..explain.chat import PositionChat
from ..explain.imbalances import Fact, extract
from ..explain.pgn import PgnError, load_pgn
from ..explain.review import Arrow, MoveReview
from ..lichess import LichessClient, LichessGame
from .board_draw import BoardDrawMixin
from .constants import (
    _FPS,
    _MIN_PANEL,
    _MIN_SQUARE,
    _TABS,
    _TUTOR_MOVE_DELAY_MS,
)
from .controller import GameController
from .dialogs import ask_pgn_text, ask_save_path
from .geometry import BoardLayout
from .panel import PanelMixin
from .pieces import PieceRenderer, load_glyph_font
from .theme import DEFAULT_THEME, Theme
from .view import current_coaching, view_eval, view_rows


class ChessTutorApp(BoardDrawMixin, PanelMixin):
    """Owns the pygame window, the render loop, and user input handling."""

    def __init__(
        self,
        controller: GameController,
        *,
        theme: Theme = DEFAULT_THEME,
        lichess_factory: Callable[[chess.Color], LichessGame] | None = None,
    ) -> None:
        self.controller = controller
        self._lichess_factory = lichess_factory
        self.theme = theme
        self.perspective = controller.human_color
        self._base_theme = theme
        self.layout = BoardLayout(theme, perspective=self.perspective)
        self.pieces = PieceRenderer(theme)
        # Resizable (and maximizable): the board scales to the window height and
        # the coaching panel takes the remaining width.
        self.screen = pygame.display.set_mode(
            (theme.window_width, theme.window_height), pygame.RESIZABLE
        )
        pygame.display.set_caption("Chess Tutor")
        self.clock = pygame.time.Clock()
        self._label_font = pygame.font.SysFont(None, 20)
        self._panel_font = pygame.font.SysFont(None, 23)
        self._bold_font = pygame.font.SysFont(None, 23, bold=True)
        self._heading_font = pygame.font.SysFont(None, 27, bold=True)
        self._small_font = pygame.font.SysFont(None, 21)
        self._badge_font = pygame.font.SysFont(None, 22, bold=True)
        self._glyph_font = load_glyph_font(20)
        self._mono_font = pygame.font.SysFont("consolas,couriernew,monospace", 15)

        self.selected: chess.Square | None = None
        self.legal_targets: list[chess.Square] = []
        self._tutor_scheduled_at: int | None = None

        self.tab = 0
        self.show_hint = False
        self.show_details = False  # D: expand every explanation
        self.show_glossary = False  # G: definitions of the terms used
        self.show_help = False  # ? / F1: keys overlay
        self.scroll = 0
        self._content_h = 0
        self._tab_rects: list[pygame.Rect] = []
        self._chat_box: pygame.Rect | None = None
        self._buttons: list[tuple[pygame.Rect, str]] = []
        self._move_rects: list[tuple[pygame.Rect, int]] = []
        self._content_clip = pygame.Rect(0, 0, 0, 0)
        self._facts_cache: tuple[str, list[Fact]] | None = None
        self._cy = 0  # virtual y cursor while drawing scrolled content
        self._last_ply_seen: tuple[int, int] = (0, 0)
        self.chat_input: str | None = None  # None = not typing
        self._skip_text = False  # swallow the key that opened the chat box
        self._flash = ""  # short notice in the footer
        self._flash_until = 0

    # -- main loop ----------------------------------------------------------- #
    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if self.chat_input is not None:
                        self._on_chat_key(event.key)
                    else:
                        self._on_key(event.key)
                elif event.type == pygame.TEXTINPUT:
                    if self.chat_input is not None:
                        if not self._skip_text:
                            self.chat_input = (self.chat_input + event.text)[:300]
                    elif event.text == "?":
                        self.show_help = not self.show_help
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._on_click(event.pos, event.button)
                elif event.type == pygame.MOUSEWHEEL:
                    self.scroll = max(0, self.scroll - event.y * 40)
                elif event.type == pygame.VIDEORESIZE:
                    self._relayout(event.w, event.h)
            self._skip_text = False

            self.controller.poll_lichess()
            self._maybe_start_tutor_turn()
            self.controller.coach_side_to_move()
            ply = (len(self.controller.board.move_stack), self.controller.view_len)
            if ply != self._last_ply_seen:  # new move / stepped: back to the top
                self._last_ply_seen = ply
                self.scroll = 0
            self._draw()
            pygame.display.flip()
            self.clock.tick(_FPS)

        pygame.display.quit()  # hide the window while we leave the Lichess game
        self.controller.close(wait=True)
        if self.controller._engine is not None:
            self.controller._engine.close()
        pygame.quit()

    # -- scheduling the tutor ------------------------------------------------ #
    def _maybe_start_tutor_turn(self) -> None:
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
            if self.show_help:
                self.show_help = False
            else:
                self._clear_selection()
        elif key == pygame.K_F1:
            self.show_help = not self.show_help
        elif key == pygame.K_f:
            self._flip_board()
        elif key == pygame.K_n:
            self._new_game()
        elif key == pygame.K_h:
            self.show_hint = not self.show_hint
        elif key == pygame.K_d:
            self.show_details = not self.show_details
        elif key == pygame.K_g:
            self.show_glossary = not self.show_glossary
            self._notify("Glossary on." if self.show_glossary else "Glossary off.", 2)
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
            self._set_tab(key - pygame.K_1)
        elif key == pygame.K_TAB:
            self._set_tab((self.tab + 1) % len(_TABS))
        elif key == pygame.K_LEFT:
            self.controller.step_view(-1)
        elif key == pygame.K_RIGHT:
            self.controller.step_view(1)
        elif key == pygame.K_HOME:
            self.controller.set_view(0)
        elif key == pygame.K_END:
            self.controller.set_view(len(self.controller.board.move_stack))
        elif key == pygame.K_i:
            self._import_pgn()
        elif key == pygame.K_e:
            self._export_pgn()
        elif key == pygame.K_c:
            self._open_chat()

    def _open_chat(self) -> None:
        self._set_tab(3)
        if self.controller.chat_client is None:
            self._notify("Chat needs OPENAI_API_KEY (+ OPENAI_BASE_URL / OPENAI_MODEL) in .env.")
            return
        self.chat_input = ""
        self._skip_text = True

    def _on_chat_key(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            self.chat_input = None
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            text = (self.chat_input or "").strip()
            if text:
                self.controller.ask_chat(text)
                self.scroll = 0
            self.chat_input = None
        elif key == pygame.K_BACKSPACE and self.chat_input:
            self.chat_input = self.chat_input[:-1]

    def _notify(self, text: str, seconds: float = 6.0) -> None:
        self._flash = text
        self._flash_until = pygame.time.get_ticks() + int(seconds * 1000)

    def _import_pgn(self) -> None:
        text = ask_pgn_text()
        if not text:
            self._notify("No PGN selected (pick a .pgn file, or copy a PGN to the clipboard first).")
            return
        try:
            board, headers = load_pgn(text)
        except PgnError as exc:
            self._notify(str(exc))
            return
        engine = self.controller._engine
        chat = self.controller.chat_client
        self.controller.close(wait=False)
        self.controller = GameController(
            engine, human_color=chess.WHITE, board=board, chat=chat, analysis_headers=headers
        )
        self._clear_selection()
        self.chat_input = None
        self.scroll = 0
        self._set_tab(0)
        self._notify(f"Imported {headers.get('White', '?')} vs {headers.get('Black', '?')} - "
                     f"reviewing {len(board.move_stack)} moves...")

    def _export_pgn(self) -> None:
        if not self.controller.board.move_stack:
            self._notify("Nothing to export yet.")
            return
        path = ask_save_path()
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.controller.export_pgn_text())
        except OSError as exc:
            self._notify(f"Could not save: {exc}")
            return
        self._notify(f"Saved annotated PGN to {path}")

    def _set_tab(self, tab: int) -> None:
        if tab != self.tab:
            self.tab = tab
            self.scroll = 0

    def _on_click(self, pos: tuple[int, int], button: int) -> None:
        if button in (4, 5):  # wheel on older pygame
            return
        if self.show_help:
            self.show_help = False
            return
        for i, rect in enumerate(self._tab_rects):
            if rect.collidepoint(pos):
                self._set_tab(i)
                return
        # Footer buttons are appended last; check them first so they win any overlap.
        for rect, action in reversed(self._buttons):
            if rect.collidepoint(pos) and (action != "play_here" or self._content_clip.collidepoint(pos)):
                if action == "import":
                    self._import_pgn()
                elif action == "export":
                    self._export_pgn()
                else:
                    self._play_from_here()
                return
        if self._content_clip.collidepoint(pos):
            for rect, ply in self._move_rects:
                if rect.collidepoint(pos):
                    self.controller.set_view(ply + 1)
                    self._clear_selection()
                    return
        if self._chat_box is not None and self._chat_box.collidepoint(pos):
            self._open_chat()
            return
        square = self.layout.square_at(*pos)
        # Browsing an earlier position: grabbing a piece of the side to move branches off there.
        c = self.controller
        if square is not None and button == 1 and not c.at_latest and c.can_play_from_here:
            piece = c.view_board.piece_at(square)
            if piece is not None and piece.color == c.view_board.turn:
                self._play_from_here()
        if self.controller.is_busy or not self.controller.is_human_turn:
            return
        if square is None:
            self._clear_selection()
            return

        # Right-click a candidate target -> "what if I played that?"
        if button == 3 and self.selected is not None and square in self.legal_targets:
            self.controller.explain_why_not(self.selected, square)
            self._set_tab(0)
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
                self.show_hint = False
            return
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

    def _play_from_here(self) -> None:
        self.controller.play_from_here()
        if self.perspective != self.controller.human_color:
            self._flip_board()
        self._clear_selection()
        self.scroll = 0
        self._notify("Playing on from this position - your move.")

    def _flip_board(self) -> None:
        self.perspective = not self.perspective
        self.layout = BoardLayout(self.theme, perspective=self.perspective)

    def _relayout(self, width: int, height: int) -> None:
        """Fit the board to the new window size; the panel gets the rest."""
        base = self._base_theme
        margin, strip = base.board_margin, base.eval_bar_strip
        by_height = (height - 2 * margin) // 8
        by_width = (width - strip - 2 * margin - _MIN_PANEL) // 8
        square = max(_MIN_SQUARE, min(by_height, by_width))
        panel = max(_MIN_PANEL, width - strip - 8 * square - 2 * margin)
        self.theme = replace(base, square_size=square, panel_width=panel)
        self.layout = BoardLayout(self.theme, perspective=self.perspective)
        self.pieces = PieceRenderer(self.theme)
        self.screen = pygame.display.get_surface()

    def _new_game(self) -> None:
        human = self.controller.human_color
        engine = self.controller._engine
        self.controller.close(wait=False)
        lichess = self._lichess_factory(human) if self._lichess_factory else None
        chat = self.controller.chat_client
        self.controller = GameController(engine, human_color=human, lichess=lichess, chat=chat)
        self.chat_input = None
        self._clear_selection()
        self._tutor_scheduled_at = None
        self.scroll = 0
        self.show_hint = False

    # -- what to show -------------------------------------------------------- #
    def _facts(self) -> list[Fact]:
        board = self.controller.view_board
        fen = board.fen()
        if self._facts_cache is None or self._facts_cache[0] != fen:
            self._facts_cache = (fen, extract(board))
        return self._facts_cache[1]

    def _latest_review(self) -> MoveReview | None:
        """Review of the move that led to the position being shown, if ready."""
        return self.controller.review_for(self.controller.view_len - 1)

    def _current_coaching(self, state):
        return current_coaching(self.controller, state)

    def _view_eval(self, state) -> tuple[int | None, int | None]:
        return view_eval(self.controller, state)

    def _view_rows(self, state):
        return view_rows(self.controller, state)

    def _overlays(self, state) -> tuple[list[Arrow], list[chess.Square]]:
        """Only the essentials by default; D adds attack arrows and fact squares."""
        arrows: list[Arrow] = []
        marks: list[chess.Square] = []
        if self.tab == 0:
            review = self._latest_review()
            if review is not None:
                keep = ("best", "reply", "attack") if self.show_details else ("best", "reply")
                arrows += [a for a in review.arrows if a.kind in keep]
                if self.show_details:
                    marks += list(review.marks)
            coaching = self._current_coaching(state)
            if coaching is not None and self.controller.is_human_turn:
                for a in coaching.arrows:
                    if a.kind == "best" and not self.show_hint:
                        continue
                    arrows.append(a)
        elif self.tab == 1:
            for f in self._facts()[: (12 if self.show_details else 5)]:
                marks += list(f.squares[:3])
        elif self.tab == 2:
            rows = self._view_rows(state)
            if rows:
                try:
                    m = chess.Move.from_uci(rows[0].move_uci)
                    arrows.append(Arrow(m.from_square, m.to_square, "best"))
                except ValueError:
                    pass
        elif self.tab == 3 and state.chat_fen == self.controller.view_board.fen():
            marks += list(state.chat_marks)
        return arrows, list(dict.fromkeys(marks))

    # -- rendering ----------------------------------------------------------- #
    def _draw(self) -> None:
        self.screen.fill(self.theme.background)
        state = self.controller.state
        arrows, marks = self._overlays(state)
        self._draw_eval_bar(state)
        self._draw_board(marks)
        self._draw_pieces()
        self._draw_arrows(arrows)
        self._draw_badge()
        self._draw_labels()
        self._draw_panel(state)

def _build_engine(settings: Settings) -> HybridEngine:
    """Construct the hybrid engine from environment settings."""
    provider = ChessApiProvider(settings.chess_api_ws_url)
    return HybridEngine.from_settings(settings, provider)


def _lichess_factory(settings: Settings) -> Callable[[chess.Color], LichessGame] | None:
    """Return a factory for Lichess games, or ``None`` to play the local engine."""
    if not settings.use_lichess:
        return None
    client = LichessClient(settings.lichess_token or "")

    def make(human_color: chess.Color) -> LichessGame:
        return LichessGame(
            client,
            bot=settings.lichess_bot,
            human_color=human_color,
            clock_limit_s=settings.lichess_clock_minutes * 60,
            increment_s=settings.lichess_increment,
        )

    return make


def main() -> None:
    """Entry point for the ``chess-tutor-gui`` script."""
    pygame.init()
    try:
        settings = load_settings()
        engine = _build_engine(settings)
        factory = _lichess_factory(settings)
        human = chess.WHITE
        lichess = factory(human) if factory else None
        chat = PositionChat.from_settings(settings)
        controller = GameController(engine, human_color=human, lichess=lichess, chat=chat)
        app = ChessTutorApp(controller, lichess_factory=factory)
        app.run()
    finally:
        if pygame.get_init():
            pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
