"""Pygame desktop front-end for the chess tutor.

A thin consumer of the shared core: python-chess validates moves,
:class:`~chess_tutor.gui.controller.GameController` runs the engine / Lichess on
background threads, and the deterministic explain layer
(:mod:`chess_tutor.explain`) produces every explanation shown here.

Controls
--------
* Click a piece, then a destination to move (auto-queens on promotion).
* Right-click a legal destination of the selected piece: "what if I played that?"
  (full review of the hypothetical move, free engine analysis, no LLM).
* ``1`` / ``2`` / ``3`` (or click the tabs): Moves / Position (Silman) / Engine.
* ``H`` shows/hides the engine's suggested move on your turn.
* Mouse wheel scrolls the panel. ``F`` flips the board, ``N`` new game, ``Esc``
  clears the selection.

Run with ``chess-tutor-gui`` or ``python -m chess_tutor.gui.app``.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable
from dataclasses import replace

import chess
import pygame

from ..config import Settings, load_settings
from ..engine.chess_api import ChessApiProvider
from ..engine.hybrid import HybridEngine
from ..engine.teaching import comparison_rows
from ..explain.chat import PositionChat
from ..explain.glossary import definitions
from ..explain.pgn import PgnError, load_pgn, summary
from ..explain.imbalances import CATEGORIES, Fact, extract, plan_ideas
from ..explain.review import Arrow, MoveReview, eval_words
from ..lichess import LichessClient, LichessGame
from .controller import GameController, _white_perspective_eval
from .geometry import BoardLayout, Rect, eval_fill_fraction
from .pieces import PieceRenderer, load_glyph_font
from .theme import DEFAULT_THEME, Theme

_FPS = 60
_TUTOR_MOVE_DELAY_MS = 350  # small pause so the player sees their move land
_TABS = ("1 Moves", "2 Position", "3 Engine")
_PAD = 16
_MIN_PANEL = 380
_MIN_SQUARE = 40


class ChessTutorApp:
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
        self._panel_font = pygame.font.SysFont(None, 22)
        self._bold_font = pygame.font.SysFont(None, 22, bold=True)
        self._heading_font = pygame.font.SysFont(None, 26, bold=True)
        self._small_font = pygame.font.SysFont(None, 19)
        self._glyph_font = load_glyph_font(20)
        self._mono_font = pygame.font.SysFont("consolas,couriernew,monospace", 15)

        self.selected: chess.Square | None = None
        self.legal_targets: list[chess.Square] = []
        self._tutor_scheduled_at: int | None = None

        self.tab = 0
        self.show_hint = False
        self.show_glossary = False  # "Words used" definitions; toggle with G
        self.scroll = 0
        self._content_h = 0
        self._tab_rects: list[pygame.Rect] = []
        self._facts_cache: tuple[str, list[Fact]] | None = None
        self._cy = 0  # virtual y cursor while drawing scrolled content
        self._last_ply_seen = 0
        self.chat_input: str | None = None  # None = chat box closed
        self._skip_text = False  # swallow the 'c' that opened the chat box
        self._flash = ""  # one-line notice (e.g. chat not configured)
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
                    if self.chat_input is not None and not self._skip_text:
                        self.chat_input = (self.chat_input + event.text)[:300]
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
            if ply != self._last_ply_seen:  # new move / stepped: jump back to the top
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
            self._clear_selection()
        elif key == pygame.K_f:
            self._flip_board()
        elif key == pygame.K_n:
            self._new_game()
        elif key == pygame.K_h:
            self.show_hint = not self.show_hint
        elif key == pygame.K_g:
            self.show_glossary = not self.show_glossary
            self._notify("Glossary on." if self.show_glossary else "Glossary off.", 2)
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3):
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
            if self.controller.chat_client is None:
                self._notify("Chat needs OPENAI_API_KEY (+ OPENAI_BASE_URL / OPENAI_MODEL) in .env.")
            else:
                self.chat_input = ""
                self._skip_text = True
                self._set_tab(0)

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
        text = _ask_pgn_text()
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
        self._notify(f"Imported {len(board.move_stack)} moves: {headers.get('White', '?')} vs "
                     f"{headers.get('Black', '?')}. Reviewing every move...")

    def _export_pgn(self) -> None:
        if not self.controller.board.move_stack:
            self._notify("Nothing to export yet.")
            return
        path = _ask_save_path()
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
        for i, rect in enumerate(self._tab_rects):
            if rect.collidepoint(pos):
                self._set_tab(i)
                return
        if self.controller.is_busy or not self.controller.is_human_turn:
            return
        square = self.layout.square_at(*pos)
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

    def _latest_review(self, state) -> MoveReview | None:
        """Review of the move that led to the position being shown, if ready."""
        return self.controller.review_for(self.controller.view_len - 1)

    def _current_coaching(self, state):
        if (
            self.controller.at_latest
            and state.coaching is not None
            and state.coaching_fen == self.controller.board.fen()
        ):
            return state.coaching
        return None

    def _view_eval(self, state) -> tuple[int | None, int | None]:
        analysis = self.controller.view_analysis()
        if analysis is not None:
            return _white_perspective_eval(analysis)
        if self.controller.at_latest:
            return state.eval_cp, state.eval_mate
        return None, None

    def _view_rows(self, state):
        if self.controller.at_latest and not self.controller.analysis_mode:
            return state.rows
        analysis = self.controller.view_analysis()
        return tuple(comparison_rows(analysis)) if analysis is not None else ()

    def _overlays(self, state) -> tuple[list[Arrow], list[chess.Square]]:
        arrows: list[Arrow] = []
        marks: list[chess.Square] = []
        if self.tab == 0:
            if state.chat_fen == self.controller.view_board.fen():
                marks += list(state.chat_marks)
            review = self._latest_review(state)
            if review is not None:
                arrows += [a for a in review.arrows if a.kind != "played"]
                marks += list(review.marks)
            coaching = self._current_coaching(state)
            if coaching is not None and self.controller.is_human_turn:
                for a in coaching.arrows:
                    if a.kind == "best" and not self.show_hint:
                        continue
                    arrows.append(a)
        elif self.tab == 1:
            for f in self._facts()[:8]:
                marks += list(f.squares[:3])
        elif self.tab == 2 and self._view_rows(state):
            try:
                m = chess.Move.from_uci(self._view_rows(state)[0].move_uci)
                arrows.append(Arrow(m.from_square, m.to_square, "best"))
            except ValueError:
                pass
        return arrows, list(dict.fromkeys(marks))

    # -- rendering ----------------------------------------------------------- #
    def _draw(self) -> None:
        self.screen.fill(self.theme.background)
        state = self.controller.state
        arrows, marks = self._overlays(state)
        self._draw_eval_bar(state)
        self._draw_board(state, marks)
        self._draw_pieces()
        self._draw_arrows(arrows)
        self._draw_labels()
        self._draw_panel(state)

    def _draw_eval_bar(self, state) -> None:
        rect = self.layout.eval_bar_rect
        eval_cp, eval_mate = self._view_eval(state)
        white_frac = eval_fill_fraction(eval_cp, eval_mate)
        pygame.draw.rect(
            self.screen, self.theme.eval_bar_black, (rect.x, rect.y, rect.width, rect.height)
        )
        white_h = round(white_frac * rect.height)
        white_y = rect.y + rect.height - white_h if self.perspective == chess.WHITE else rect.y
        if white_h > 0:
            pygame.draw.rect(
                self.screen, self.theme.eval_bar_white, (rect.x, white_y, rect.width, white_h)
            )
        mid_y = rect.y + rect.height // 2
        pygame.draw.line(
            self.screen, self.theme.eval_bar_midline, (rect.x, mid_y), (rect.x + rect.width, mid_y), 1
        )
        pygame.draw.rect(
            self.screen, self.theme.eval_bar_border, (rect.x, rect.y, rect.width, rect.height), 1
        )
        label = self._eval_label_text(eval_cp, eval_mate)
        if label:
            white_leads = white_frac >= 0.5
            colour = self.theme.eval_bar_black if white_leads else self.theme.eval_bar_white
            surf = self._small_font.render(label, True, colour)
            at_bottom = white_leads == (self.perspective == chess.WHITE)
            y = rect.y + rect.height - surf.get_height() - 3 if at_bottom else rect.y + 3
            self.screen.blit(surf, (rect.x + (rect.width - surf.get_width()) // 2, y))

    @staticmethod
    def _eval_label_text(eval_cp: int | None, eval_mate: int | None) -> str:
        if eval_mate is not None:
            return f"M{abs(eval_mate)}"
        if eval_cp is None:
            return ""
        return f"{eval_cp / 100:+.1f}"

    def _draw_board(self, state, marks: list[chess.Square]) -> None:
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
        for square in marks:
            rect = self.layout.square_rect(square)
            pygame.draw.rect(
                self.screen, self.theme.mark, (rect.x + 2, rect.y + 2, rect.width - 4, rect.height - 4), 4
            )
        self._draw_move_hints()

    def _draw_arrows(self, arrows: list[Arrow]) -> None:
        if not arrows:
            return
        colours = {
            "played": self.theme.arrow_played,
            "best": self.theme.arrow_best,
            "reply": self.theme.arrow_reply,
            "attack": self.theme.arrow_attack,
        }
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        size = self.theme.square_size
        for arrow in arrows:
            if arrow.from_sq == arrow.to_sq:
                continue
            colour = (*colours.get(arrow.kind, self.theme.arrow_played), self.theme.arrow_alpha)
            x1, y1 = self.layout.square_rect(arrow.from_sq).center
            x2, y2 = self.layout.square_rect(arrow.to_sq).center
            angle = math.atan2(y2 - y1, x2 - x1)
            head = size * 0.38
            width = max(6, size // 8)
            # Stop the shaft where the head starts.
            sx, sy = x2 - math.cos(angle) * head, y2 - math.sin(angle) * head
            pygame.draw.line(overlay, colour, (x1, y1), (sx, sy), width)
            left = (sx + math.cos(angle + math.pi / 2) * head * 0.6,
                    sy + math.sin(angle + math.pi / 2) * head * 0.6)
            right = (sx + math.cos(angle - math.pi / 2) * head * 0.6,
                     sy + math.sin(angle - math.pi / 2) * head * 0.6)
            pygame.draw.polygon(overlay, colour, [(x2, y2), left, right])
        self.screen.blit(overlay, (0, 0))

    def _draw_move_hints(self) -> None:
        board = self.controller.board
        for target in self.legal_targets:
            rect = self.layout.square_rect(target)
            cx, cy = rect.center
            if board.piece_at(target) is not None:
                pygame.draw.circle(
                    self.screen, self.theme.legal_ring, (cx, cy), rect.width // 2 - 3, 4
                )
            else:
                dot = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                pygame.draw.circle(
                    dot, (*self.theme.legal_dot, 90), (rect.width // 2, rect.height // 2), rect.width // 6
                )
                self.screen.blit(dot, (rect.x, rect.y))

    def _draw_pieces(self) -> None:
        board = self.controller.view_board
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece is not None:
                self.pieces.blit_centered(self.screen, piece, self.layout.square_rect(square).center)

    def _draw_labels(self) -> None:
        for letter, x, y in self.layout.file_label_positions():
            surf = self._label_font.render(letter, True, self.theme.label)
            self.screen.blit(surf, surf.get_rect(center=(x, y + 8)))
        for digit, x, y in self.layout.rank_label_positions():
            surf = self._label_font.render(digit, True, self.theme.label)
            self.screen.blit(surf, surf.get_rect(center=(x, y)))

    # -- panel --------------------------------------------------------------- #
    def _draw_panel(self, state) -> None:
        p = self.layout.panel_rect
        panel = Rect(p.x, 0, max(p.width, self.screen.get_width() - p.x), self.screen.get_height())
        pygame.draw.rect(self.screen, self.theme.panel_bg, (panel.x, panel.y, panel.width, panel.height))
        x = panel.x + _PAD
        y = 12

        # Fixed header: status, clocks, evaluation in words, tabs.
        status_colour = self.theme.status_thinking if state.thinking else self.theme.panel_text
        y = self._fixed_text(state.status, self._heading_font, status_colour, x, y)
        clocks = self.controller.clock_texts()
        if clocks is not None:
            you, opp = clocks
            y = self._fixed_text(
                f"vs {self.controller.opponent_name} (Lichess)    You {you}    Bot {opp}",
                self._panel_font, self.theme.panel_text, x, y,
            )
        eval_cp, eval_mate = self._view_eval(state)
        white_cp = eval_cp
        if eval_mate is not None:
            white_cp = (10_000 - abs(eval_mate)) * (1 if eval_mate > 0 else -1)
        if white_cp is not None:
            y = self._fixed_text(f"Eval: {eval_words(white_cp)}", self._panel_font, self.theme.panel_muted, x, y)
        if not self.controller.at_latest or self.controller.analysis_mode:
            n = len(self.controller.board.move_stack)
            y = self._fixed_text(
                f"Viewing move {self.controller.view_len} of {n}   (Left/Right, Home/End)",
                self._panel_font, self.theme.status_thinking, x, y,
            )
        y += 4
        self._tab_rects = []
        tx = x
        for i, name in enumerate(_TABS):
            surf = self._panel_font.render(name, True, self.theme.panel_text)
            rect = pygame.Rect(tx, y, surf.get_width() + 18, surf.get_height() + 10)
            pygame.draw.rect(self.screen, self.theme.tab_active if i == self.tab else self.theme.tab_bg, rect, border_radius=5)
            self.screen.blit(surf, (tx + 9, y + 5))
            self._tab_rects.append(rect)
            tx = rect.right + 6
        y += self._tab_rects[0].height + 8

        # Scrollable content.
        footer_h = 26 + (40 if self.chat_input is not None else 0)
        clip = pygame.Rect(panel.x, y, panel.width, panel.height - y - footer_h)
        self.screen.set_clip(clip)
        self._clip_top = y
        self._cy = y
        if self.tab == 0:
            self._draw_moves_tab(state, x, panel)
        elif self.tab == 1:
            self._draw_position_tab(x, panel)
        else:
            self._draw_engine_tab(state, x, panel)
        self._content_h = self._cy - y
        self.screen.set_clip(None)
        max_scroll = max(0, self._content_h - clip.height)
        self.scroll = min(self.scroll, max_scroll)
        if max_scroll:
            frac = self.scroll / max_scroll
            bar_h = max(30, clip.height * clip.height // max(1, self._content_h))
            by = clip.y + int((clip.height - bar_h) * frac)
            pygame.draw.rect(self.screen, self.theme.tab_bg, (panel.x + panel.width - 6, by, 4, bar_h))

        if self.chat_input is not None:
            box = pygame.Rect(x, panel.height - footer_h + 2, panel.width - 2 * _PAD, 34)
            pygame.draw.rect(self.screen, self.theme.tab_bg, box, border_radius=5)
            pygame.draw.rect(self.screen, self.theme.panel_heading, box, 2, border_radius=5)
            shown = "Ask: " + self.chat_input + ("|" if (pygame.time.get_ticks() // 500) % 2 else " ")
            surf = self._panel_font.render(shown, True, self.theme.panel_text)
            # Keep the end of long questions visible.
            offset = max(0, surf.get_width() - (box.width - 16))
            self.screen.set_clip(box.inflate(-8, -4))
            self.screen.blit(surf, (box.x + 8 - offset, box.y + 9))
            self.screen.set_clip(None)
        new_hint = "N: resign+new" if self.controller.lichess_snapshot else "N: new"
        if self._flash and pygame.time.get_ticks() > self._flash_until:
            self._flash = ""
        hint = self._flash or (
            f"C: chat  R-click: what if?  H: hint  </>: browse  I/E: PGN in/out  {new_hint}"
        )
        if self.chat_input is not None:
            hint = "Type your question - Enter: send   Esc: cancel"
        surf = self._small_font.render(hint, True, self.theme.panel_muted)
        self.screen.blit(surf, (x, panel.height - 22))

    def _fixed_text(self, text, font, colour, x: int, y: int) -> int:
        surf = font.render(text, True, colour)
        self.screen.blit(surf, (x, y))
        return y + surf.get_height() + 3

    # Scrolled content helpers (draw at the virtual cursor minus scroll).
    def _w(self, text: str, font=None, colour=None, *, indent: int = 0, gap: int = 2) -> None:
        font = font or self._small_font
        colour = colour or self.theme.panel_text
        panel = self.layout.panel_rect
        x = panel.x + _PAD + indent
        max_w = panel.width - 2 * _PAD - indent
        for line in _wrap(text, font, max_w):
            surf = font.render(line, True, colour)
            self.screen.blit(surf, (x, self._cy - self.scroll))
            self._cy += surf.get_height() + 1
        self._cy += gap

    def _bullet(self, text: str, colour=None, *, indent: int = 8) -> None:
        sign_colour = colour
        body = text
        if text.startswith("+ "):
            sign_colour, body = self.theme.good_text, "+ " + text[2:]
        elif text.startswith("- "):
            sign_colour, body = self.theme.bad_text, "- " + text[2:]
        elif not text.endswith(":"):
            body = "\u00b7 " + text
        self._w(body, self._small_font, sign_colour or self.theme.panel_text, indent=indent)

    def _heading(self, text: str) -> None:
        self._cy += 4
        self._w(text, self._bold_font, self.theme.panel_heading, gap=4)

    def _label_colour(self, label: str):
        if label in ("Best", "Excellent", "Checkmate"):
            return self.theme.good_text
        if label == "Good":
            return self.theme.panel_text
        if label == "Inaccuracy":
            return self.theme.warn_text
        if label in ("Mistake", "Blunder"):
            return self.theme.bad_text
        return self.theme.panel_text

    def _draw_review(self, review: MoveReview) -> None:
        who = self.controller.side_name(review.color)
        self._w(f"{who}: {review.title}", self._bold_font, self._label_colour(review.label), gap=1)
        self._w(review.eval_text[0].upper() + review.eval_text[1:] + ".", self._small_font, self.theme.panel_muted, indent=8)
        for point in review.points:
            self._bullet(point)
        if review.problem:
            self._bullet("Problem: " + review.problem, self.theme.bad_text)
        if review.better:
            self._bullet(review.better, self.theme.good_text)
        self._cy += 6

    def _draw_chat(self, state) -> None:
        if state.chat_fen != self.controller.view_board.fen() or not state.chat:
            return
        self._heading("Coach chat (AI - grounded in the facts below)")
        for role, text in state.chat[-6:]:
            if role == "user":
                self._w("You: " + text, self._small_font, self.theme.panel_muted)
            else:
                self._w(text, self._small_font, self.theme.panel_text)
        if state.chat_busy:
            self._w("Thinking...", self._small_font, self.theme.status_thinking)
        elif state.chat_marks:
            self._w("Blue squares = what the answer cites.", self._small_font, self.theme.panel_muted)

    def _draw_moves_tab(self, state, x: int, panel) -> None:
        terms: list[str] = []
        self._draw_chat(state)
        if state.headline:
            self._w(state.headline, self._panel_font, self.theme.panel_heading)
        if state.narrative:
            for para in state.narrative.split("\n"):
                self._w(para, self._small_font, self.theme.panel_text)

        if self.controller.analysis_mode:
            self._draw_game_summary()

        # Reviews of the last two moves up to the viewed position (newest first).
        v = self.controller.view_len
        if v:
            self._heading("Move review")
            reviews = [
                r for r in (self.controller.review_for(v - 1), self.controller.review_for(v - 2))
                if r is not None
            ]
            if self._latest_review(state) is None:
                self._w("Analysing this move...", self._small_font, self.theme.status_thinking)
            for review in reviews:
                self._draw_review(review)
                terms += list(review.terms)

        coaching = self._current_coaching(state)
        if coaching is not None and self.controller.is_human_turn:
            self._heading("Your turn")
            for warning in coaching.warnings:
                self._bullet(warning, self.theme.warn_text)
            if coaching.plans:
                self._w("Plan ideas from the imbalances (Silman):", self._small_font, self.theme.panel_muted)
                for plan in coaching.plans:
                    self._bullet(plan)
            if self.show_hint:
                self._bullet(coaching.best_text, self.theme.good_text)
            else:
                self._w("Press H to reveal the engine's move.", self._small_font, self.theme.panel_muted)
            terms += list(coaching.terms)
        self._draw_glossary(terms)

    def _draw_game_summary(self) -> None:
        reviews = self.controller.reviews_snapshot()
        total = len(self.controller.board.move_stack)
        self._heading(f"Game summary ({len(reviews)}/{total} moves reviewed)")
        counts = summary(reviews)
        for color in (chess.WHITE, chess.BLACK):
            c = counts[color]
            self._w(
                f"{self.controller.side_name(color)} ({'White' if color else 'Black'}): "
                f"{c['Inaccuracy']} inaccuracies, {c['Mistake']} mistakes, {c['Blunder']} blunders",
                self._small_font, self.theme.panel_text,
            )
        worst = sorted(
            (r for r in reviews.values() if r.label in ("Mistake", "Blunder")),
            key=lambda r: -(r.win_drop or 0),
        )[:4]
        if worst:
            self._w("Biggest turning points (Home, then Right to step there):", self._small_font,
                    self.theme.panel_muted)
            for r in worst:
                self._bullet(f"{r.title} ({self.controller.side_name(r.color)})",
                             self._label_colour(r.label))

    def _draw_position_tab(self, x: int, panel) -> None:
        board = self.controller.view_board
        facts = self._facts()
        self._heading("Imbalances (Silman)")
        if not facts:
            self._w("No clear imbalances yet: the position is symmetrical.", self._small_font, self.theme.panel_muted)
        for category in CATEGORIES:
            group = [f for f in facts if f.category == category]
            if not group:
                continue
            self._w(category.capitalize(), self._panel_font, self.theme.panel_heading, gap=1)
            for f in group:
                colour = (
                    self.theme.good_text if f.good_for == self.controller.human_color
                    else self.theme.bad_text if f.good_for is not None else self.theme.panel_text
                )
                self._bullet(f.text, colour)
        me = self.controller.human_color
        for color, title in ((me, "Plan ideas for you"), (not me, f"Plan ideas for {self.controller.opponent_name}")):
            ideas = plan_ideas(board, facts, color)
            if ideas:
                self._heading(title)
                for text, _sq in ideas:
                    self._bullet(text)
        self._w("Green = good for you, red = good for the opponent. Blue squares on the "
                "board show what the top facts are about.", self._small_font, self.theme.panel_muted)
        self._draw_glossary([t for f in facts for t in f.terms] + ["imbalance"])

    def _draw_engine_tab(self, state, x: int, panel) -> None:
        self._heading("Engine candidates")
        rows = self._view_rows(state)
        if not rows:
            self._w("No analysis yet.", self._small_font, self.theme.panel_muted)
        for row in rows[:6]:
            marker = "=" if row.is_best else " "
            loss = "" if row.loss_cp == 0 else f"  -{row.loss_cp}cp"
            colour = self.theme.panel_heading if row.is_best else self.theme.panel_text
            self._w(f"{marker} {row.rank}. {row.move:<7} {row.score}{loss}", self._mono_font, colour, gap=0)
            if row.pv_san or row.pv:
                self._w(f"   {row.pv_san or row.pv}", self._small_font, self.theme.panel_muted, indent=12)
        self._heading("Material")
        white_cap, black_cap = self._captured_pieces()
        self._w(f"White has taken: {''.join(white_cap) or '-'}", self._glyph_font)
        self._w(f"Black has taken: {''.join(black_cap) or '-'}", self._glyph_font)
        self._heading("Moves")
        for text in self._san_move_rows(limit=200):
            self._w(text, self._mono_font, self.theme.panel_text, gap=0)
        self._draw_glossary(["centipawn"])

    def _draw_glossary(self, terms: list[str]) -> None:
        if not self.show_glossary:
            return
        defs = definitions(terms)
        if not defs:
            return
        self._heading("Words used")
        for term, text in defs[:8]:
            self._w(f"{term.capitalize()}: {text}", self._small_font, self.theme.panel_muted, indent=4)

    def _san_move_rows(self, *, limit: int) -> list[str]:
        board = self.controller.board
        replay = chess.Board()
        sans: list[str] = []
        for move in board.move_stack:
            sans.append(replay.san(move))
            replay.push(move)
        rows: list[str] = []
        for i in range(0, len(sans), 2):
            black = sans[i + 1] if i + 1 < len(sans) else ""
            rows.append(f"{i // 2 + 1:>2}. {sans[i]:<8}{black}")
        return rows[-limit:]

    # -- small helpers -------------------------------------------------------- #
    def _tint(self, rect, colour: tuple[int, int, int]) -> None:
        overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        overlay.fill((*colour, self.theme.overlay_alpha))
        self.screen.blit(overlay, (rect.x, rect.y))

    def _last_move_squares(self, state) -> set[chess.Square]:
        board = self.controller.view_board
        if not board.move_stack:
            return set()
        move = board.peek()
        return {move.from_square, move.to_square}

    def _king_in_check_square(self) -> chess.Square | None:
        board = self.controller.view_board
        return board.king(board.turn) if board.is_check() else None

    def _captured_pieces(self) -> tuple[list[str], list[str]]:
        board = self.controller.view_board
        start = {chess.PAWN: 8, chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 2, chess.QUEEN: 1}
        glyphs = {chess.PAWN: "♟", chess.KNIGHT: "♞", chess.BISHOP: "♝", chess.ROOK: "♜", chess.QUEEN: "♛"}
        by_white: list[str] = []
        by_black: list[str] = []
        for ptype, count in start.items():
            by_white += glyphs[ptype] * max(0, count - len(board.pieces(ptype, chess.BLACK)))
            by_black += glyphs[ptype] * max(0, count - len(board.pieces(ptype, chess.WHITE)))
        return by_white, by_black


def _tk_root():
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def _ask_pgn_text() -> str | None:
    """File picker for a .pgn; if cancelled, fall back to a PGN on the clipboard."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = _tk_root()
    except Exception:  # noqa: BLE001 - no Tk available
        return None
    try:
        path = filedialog.askopenfilename(
            parent=root, title="Import PGN", filetypes=[("PGN files", "*.pgn"), ("All files", "*.*")]
        )
        if path:
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        try:
            clip = root.clipboard_get()
        except tk.TclError:
            clip = ""
        return clip if "1." in clip else None
    finally:
        root.destroy()


def _ask_save_path() -> str | None:
    try:
        from tkinter import filedialog

        root = _tk_root()
    except Exception:  # noqa: BLE001
        return None
    try:
        return filedialog.asksaveasfilename(
            parent=root,
            title="Export annotated PGN",
            defaultextension=".pgn",
            initialfile="chess-tutor-game.pgn",
            filetypes=[("PGN files", "*.pgn")],
        ) or None
    finally:
        root.destroy()


def _wrap(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Greedy word-wrap ``text`` to ``max_width`` pixels for ``font``."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split(" "):
            trial = f"{current} {word}".strip()
            if font.size(trial)[0] <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        lines.append(current)
    return lines


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
