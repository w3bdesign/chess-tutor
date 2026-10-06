"""Unit tests for the pure GUI layout math (no pygame, no network)."""

from __future__ import annotations

import chess

from chess_tutor.gui.geometry import BoardLayout, Rect
from chess_tutor.gui.theme import DEFAULT_THEME, Theme


def test_rect_center_and_contains() -> None:
    rect = Rect(10, 20, 40, 60)
    assert rect.center == (30, 50)
    assert rect.contains(10, 20)  # top-left inclusive
    assert rect.contains(49, 79)  # inside
    assert not rect.contains(50, 80)  # bottom-right exclusive
    assert not rect.contains(9, 20)


def test_square_rect_white_perspective_corners() -> None:
    theme = DEFAULT_THEME
    layout = BoardLayout(theme, perspective=chess.WHITE)
    origin = theme.board_margin
    size = theme.square_size

    # A8 is top-left for White.
    a8 = layout.square_rect(chess.A8)
    assert (a8.x, a8.y) == (origin, origin)

    # H1 is bottom-right for White.
    h1 = layout.square_rect(chess.H1)
    assert (h1.x, h1.y) == (origin + 7 * size, origin + 7 * size)

    # A1 is bottom-left for White.
    a1 = layout.square_rect(chess.A1)
    assert (a1.x, a1.y) == (origin, origin + 7 * size)


def test_square_rect_black_perspective_is_mirrored() -> None:
    theme = DEFAULT_THEME
    layout = BoardLayout(theme, perspective=chess.BLACK)
    origin = theme.board_margin
    size = theme.square_size

    # The Black view is a 180-degree rotation of the White view: H1 is top-left.
    h1 = layout.square_rect(chess.H1)
    assert (h1.x, h1.y) == (origin, origin)

    # A8 is bottom-right for Black.
    a8 = layout.square_rect(chess.A8)
    assert (a8.x, a8.y) == (origin + 7 * size, origin + 7 * size)


def test_square_at_is_inverse_of_square_rect_both_perspectives() -> None:
    for perspective in (chess.WHITE, chess.BLACK):
        layout = BoardLayout(DEFAULT_THEME, perspective=perspective)
        for square in chess.SQUARES:
            rect = layout.square_rect(square)
            cx, cy = rect.center
            assert layout.square_at(cx, cy) == square


def test_square_at_off_board_returns_none() -> None:
    layout = BoardLayout(DEFAULT_THEME, perspective=chess.WHITE)
    # Inside the right-hand panel, well past the board.
    panel = layout.panel_rect
    assert layout.square_at(panel.x + 10, 40) is None
    # Above/left of the board origin.
    assert layout.square_at(0, 0) is None


def test_file_and_rank_labels_cover_all_eight() -> None:
    layout = BoardLayout(DEFAULT_THEME, perspective=chess.WHITE)
    files = [letter for letter, _, _ in layout.file_label_positions()]
    ranks = [digit for digit, _, _ in layout.rank_label_positions()]
    assert files == list("abcdefgh")
    assert ranks == list("87654321")  # top-to-bottom for White


def test_labels_flip_with_perspective() -> None:
    layout = BoardLayout(DEFAULT_THEME, perspective=chess.BLACK)
    files = [letter for letter, _, _ in layout.file_label_positions()]
    ranks = [digit for digit, _, _ in layout.rank_label_positions()]
    assert files == list("hgfedcba")
    assert ranks == list("12345678")


def test_panel_rect_is_right_of_board() -> None:
    theme = DEFAULT_THEME
    layout = BoardLayout(theme, perspective=chess.WHITE)
    panel = layout.panel_rect
    board_right = theme.board_margin + theme.board_size + theme.board_margin
    assert panel.x == board_right
    assert panel.width == theme.panel_width
    assert panel.height == theme.window_height


def test_theme_dimensions_are_consistent() -> None:
    theme = Theme()
    assert theme.board_size == theme.square_size * 8
    assert theme.window_width == theme.board_size + theme.board_margin * 2 + theme.panel_width
    assert theme.window_height == theme.board_size + theme.board_margin * 2
