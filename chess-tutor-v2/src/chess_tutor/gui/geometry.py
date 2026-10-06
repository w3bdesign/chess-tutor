"""Pure board/layout coordinate math for the Pygame front-end.

This module has **no pygame and no network dependency** so every function here is
trivially unit-testable. It maps between:

* chess squares (``python-chess`` 0..63 indices, A1 == 0, H8 == 63), and
* on-screen pixel rectangles,

taking the board ``perspective`` (whose side is at the bottom) into account.

The rest of the GUI defers all of its hit-testing and drawing coordinates to the
helpers here, so the "which square did the user click?" logic lives in exactly
one place.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from .theme import Theme


@dataclass(frozen=True)
class Rect:
    """An axis-aligned rectangle in window pixel coordinates."""

    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


class BoardLayout:
    """Maps chess squares to pixel rectangles for a given theme + perspective."""

    def __init__(self, theme: Theme, *, perspective: chess.Color = chess.WHITE) -> None:
        self.theme = theme
        self.perspective = perspective

    # -- square <-> grid cell ------------------------------------------------ #
    def _file_rank_to_cell(self, file: int, rank: int) -> tuple[int, int]:
        """Grid column/row (0,0 == top-left) for a board ``file``/``rank``."""
        if self.perspective == chess.WHITE:
            col = file
            row = 7 - rank
        else:
            col = 7 - file
            row = rank
        return col, row

    def _cell_to_file_rank(self, col: int, row: int) -> tuple[int, int]:
        if self.perspective == chess.WHITE:
            file = col
            rank = 7 - row
        else:
            file = 7 - col
            rank = row
        return file, rank

    # -- public API ---------------------------------------------------------- #
    def square_rect(self, square: chess.Square) -> Rect:
        """Pixel rectangle covering ``square``."""
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        col, row = self._file_rank_to_cell(file, rank)
        size = self.theme.square_size
        origin = self.theme.board_margin
        return Rect(origin + col * size, origin + row * size, size, size)

    def square_at(self, px: int, py: int) -> chess.Square | None:
        """Return the square under pixel ``(px, py)`` or ``None`` if off-board."""
        origin = self.theme.board_margin
        size = self.theme.square_size
        local_x = px - origin
        local_y = py - origin
        if local_x < 0 or local_y < 0:
            return None
        col = local_x // size
        row = local_y // size
        if col > 7 or row > 7:
            return None
        file, rank = self._cell_to_file_rank(int(col), int(row))
        return chess.square(file, rank)

    def file_label_positions(self) -> list[tuple[str, int, int]]:
        """``(letter, x, y)`` anchor points for the file labels (a..h)."""
        size = self.theme.square_size
        origin = self.theme.board_margin
        baseline = origin + self.theme.board_size + 2
        out: list[tuple[str, int, int]] = []
        for col in range(8):
            file, _ = self._cell_to_file_rank(col, 0)
            letter = chess.FILE_NAMES[file]
            x = origin + col * size + size // 2
            out.append((letter, x, baseline))
        return out

    def rank_label_positions(self) -> list[tuple[str, int, int]]:
        """``(digit, x, y)`` anchor points for the rank labels (1..8)."""
        size = self.theme.square_size
        origin = self.theme.board_margin
        x = origin - 12
        out: list[tuple[str, int, int]] = []
        for row in range(8):
            _, rank = self._cell_to_file_rank(0, row)
            digit = chess.RANK_NAMES[rank]
            y = origin + row * size + size // 2
            out.append((digit, x, y))
        return out

    @property
    def panel_rect(self) -> Rect:
        """Rectangle of the coaching side panel to the right of the board."""
        origin = self.theme.board_margin
        left = origin + self.theme.board_size + origin
        return Rect(left, 0, self.theme.panel_width, self.theme.window_height)
