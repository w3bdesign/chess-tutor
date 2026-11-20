"""Board rendering: squares, highlights, arrows, badges, pieces, eval bar."""

from __future__ import annotations

import math

import chess
import pygame

from ..explain.review import LABEL_SYMBOL, Arrow
from .geometry import eval_fill_fraction
from .text import eval_label


class BoardDrawMixin:
    """Drawing methods for the board area; mixed into ChessTutorApp."""

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
        label = eval_label(eval_cp, eval_mate)
        if label:
            white_leads = white_frac >= 0.5
            colour = self.theme.eval_bar_black if white_leads else self.theme.eval_bar_white
            surf = self._label_font.render(label, True, colour)
            at_bottom = white_leads == (self.perspective == chess.WHITE)
            y = rect.y + rect.height - surf.get_height() - 3 if at_bottom else rect.y + 3
            self.screen.blit(surf, (rect.x + (rect.width - surf.get_width()) // 2, y))

    def _draw_board(self, marks: list[chess.Square]) -> None:
        last_move = self._last_move_squares()
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
                self.screen, self.theme.mark, (rect.x + 2, rect.y + 2, rect.width - 4, rect.height - 4), 3
            )
        self._draw_move_hints()

    def _draw_badge(self) -> None:
        """chess.com-style quality badge on the destination square of the shown move."""
        review = self._latest_review()
        if review is None or review.label not in ("Best", "Inaccuracy", "Mistake", "Blunder", "Checkmate"):
            return
        colour = {
            "Best": self.theme.good_text,
            "Checkmate": self.theme.good_text,
            "Inaccuracy": self.theme.warn_text,
            "Mistake": (235, 140, 60),
            "Blunder": self.theme.bad_text,
        }[review.label]
        to_sq = chess.Move.from_uci(review.move_uci).to_square
        rect = self.layout.square_rect(to_sq)
        radius = max(10, self.theme.square_size // 6)
        cx, cy = rect.x + rect.width - radius + 3, rect.y + radius - 3
        pygame.draw.circle(self.screen, (30, 30, 30), (cx, cy), radius + 2)
        pygame.draw.circle(self.screen, colour, (cx, cy), radius)
        surf = self._badge_font.render(LABEL_SYMBOL.get(review.label, "") or "!", True, (20, 20, 20))
        self.screen.blit(surf, surf.get_rect(center=(cx, cy + 1)))

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

    # -- small helpers -------------------------------------------------------- #
    def _tint(self, rect, colour: tuple[int, int, int]) -> None:
        overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        overlay.fill((*colour, self.theme.overlay_alpha))
        self.screen.blit(overlay, (rect.x, rect.y))

    def _last_move_squares(self) -> set[chess.Square]:
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
