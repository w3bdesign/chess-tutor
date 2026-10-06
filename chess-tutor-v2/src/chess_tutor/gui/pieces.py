"""Unicode-glyph chess piece rendering for the Pygame front-end.

Rather than download PNG sprites at launch (an extra network dependency and a
heavyweight image stack), pieces are drawn from the Unicode chess glyphs using a
system font. We use the *filled* glyph for every piece and tint it by colour --
white pieces light, black pieces dark -- which renders far more crisply and
consistently across platforms than mixing the outline (♙) and filled (♟) glyphs.

Rendered surfaces are cached per ``(symbol, size)`` so the event loop never pays
to re-rasterise a glyph it has already drawn.
"""

from __future__ import annotations

import chess
import pygame

from .theme import Theme

# Filled glyph per piece *type*; colour is applied via the font fill, not the
# glyph choice, so both sides use the same solid shape.
_TYPE_GLYPH = {
    chess.PAWN: "\u265f",  # ♟
    chess.KNIGHT: "\u265e",  # ♞
    chess.BISHOP: "\u265d",  # ♝
    chess.ROOK: "\u265c",  # ♜
    chess.QUEEN: "\u265b",  # ♛
    chess.KING: "\u265a",  # ♚
}

# Fonts that are known to carry the chess glyphs, tried in order. ``None`` (the
# pygame default font) is the final fallback so we always render *something*.
_FONT_CANDIDATES = (
    "Segoe UI Symbol",  # Windows
    "DejaVu Sans",  # Linux
    "Arial Unicode MS",  # macOS / Office
    "FreeSerif",
)


class PieceRenderer:
    """Rasterises and caches piece glyphs for a given square size."""

    def __init__(self, theme: Theme) -> None:
        self._theme = theme
        self._font = self._load_font(int(theme.square_size * 0.82))
        # Cache keyed by the piece symbol ("P", "n", ...).
        self._cache: dict[str, pygame.Surface] = {}

    @staticmethod
    def _load_font(size: int) -> pygame.font.Font:
        for name in _FONT_CANDIDATES:
            match = pygame.font.match_font(name)
            if match:
                return pygame.font.Font(match, size)
        return pygame.font.SysFont(None, size)

    def surface_for(self, piece: chess.Piece) -> pygame.Surface:
        """Return a cached, colour-tinted surface for ``piece``."""
        key = piece.symbol()
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        glyph = _TYPE_GLYPH[piece.piece_type]
        colour = self._theme.piece_light if piece.color == chess.WHITE else self._theme.piece_dark
        # A subtle outline in the opposite tone keeps light pieces readable on
        # light squares and dark pieces readable on dark squares.
        outline = self._theme.piece_dark if piece.color == chess.WHITE else self._theme.piece_light
        surface = self._render_with_outline(glyph, colour, outline)
        self._cache[key] = surface
        return surface

    def _render_with_outline(
        self, glyph: str, colour: tuple[int, int, int], outline: tuple[int, int, int]
    ) -> pygame.Surface:
        base = self._font.render(glyph, True, colour)
        halo = self._font.render(glyph, True, outline)
        w, h = base.get_size()
        canvas = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
        # Draw the halo offset in four directions, then the fill on top.
        for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
            canvas.blit(halo, (dx, dy))
        canvas.blit(base, (1, 1))
        return canvas

    def blit_centered(
        self, target: pygame.Surface, piece: chess.Piece, center: tuple[int, int]
    ) -> None:
        """Blit ``piece`` centred on ``center`` onto ``target``."""
        surface = self.surface_for(piece)
        rect = surface.get_rect(center=center)
        target.blit(surface, rect)
