"""Colours, fonts and sizing constants for the Pygame front-end.

Kept free of any pygame import so it can be read/tested anywhere. Colours are
plain ``(r, g, b)`` tuples that pygame accepts directly.
"""

from __future__ import annotations

from dataclasses import dataclass

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    """Visual configuration for the board and side panel."""

    # Board sizing.
    square_size: int = 80
    board_margin: int = 24  # space around the board for rank/file labels
    panel_width: int = 360  # coaching panel to the right of the board

    # Board colours -- chess.com's default "Green" board.
    light_square: RGB = (235, 236, 208)  # #EBECD0
    dark_square: RGB = (115, 149, 82)  # #739552

    # Overlays (chess.com page chrome + highlights).
    background: RGB = (49, 46, 43)  # #312E2B
    panel_bg: RGB = (38, 36, 33)  # #262421
    selected: RGB = (245, 246, 130)  # yellow highlight for the picked-up piece
    last_move: RGB = (245, 246, 130)  # same yellow for the previous move
    legal_dot: RGB = (0, 0, 0)  # move-target dots on empty squares (translucent)
    legal_ring: RGB = (0, 0, 0)  # ring around capturable pieces (translucent)
    check: RGB = (235, 97, 80)  # king-in-check square tint

    # Text / pieces.
    piece_light: RGB = (248, 248, 248)
    piece_dark: RGB = (38, 33, 28)
    label: RGB = (180, 180, 170)
    panel_text: RGB = (230, 230, 226)
    panel_heading: RGB = (124, 192, 95)  # chess.com green accent
    panel_muted: RGB = (150, 150, 144)
    status_thinking: RGB = (240, 200, 90)

    # Alpha used for the translucent move/legal overlays.
    overlay_alpha: int = 110

    @property
    def board_size(self) -> int:
        """Pixel size of the 8x8 board grid (without labels)."""
        return self.square_size * 8

    @property
    def window_width(self) -> int:
        return self.board_size + self.board_margin * 2 + self.panel_width

    @property
    def window_height(self) -> int:
        return self.board_size + self.board_margin * 2


DEFAULT_THEME = Theme()
