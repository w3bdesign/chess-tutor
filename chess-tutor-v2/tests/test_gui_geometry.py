"""Unit tests for the pure GUI layout math (no pygame, no network)."""

from __future__ import annotations

import chess

from chess_tutor.gui.geometry import BoardLayout, Rect, eval_fill_fraction
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
    origin_x = theme.board_left
    origin_y = theme.board_margin
    size = theme.square_size

    # A8 is top-left for White.
    a8 = layout.square_rect(chess.A8)
    assert (a8.x, a8.y) == (origin_x, origin_y)

    # H1 is bottom-right for White.
    h1 = layout.square_rect(chess.H1)
    assert (h1.x, h1.y) == (origin_x + 7 * size, origin_y + 7 * size)

    # A1 is bottom-left for White.
    a1 = layout.square_rect(chess.A1)
    assert (a1.x, a1.y) == (origin_x, origin_y + 7 * size)


def test_square_rect_black_perspective_is_mirrored() -> None:
    theme = DEFAULT_THEME
    layout = BoardLayout(theme, perspective=chess.BLACK)
    origin_x = theme.board_left
    origin_y = theme.board_margin
    size = theme.square_size

    # The Black view is a 180-degree rotation of the White view: H1 is top-left.
    h1 = layout.square_rect(chess.H1)
    assert (h1.x, h1.y) == (origin_x, origin_y)

    # A8 is bottom-right for Black.
    a8 = layout.square_rect(chess.A8)
    assert (a8.x, a8.y) == (origin_x + 7 * size, origin_y + 7 * size)


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
    # Inside the eval bar on the far left is off-board too.
    bar = layout.eval_bar_rect
    assert layout.square_at(bar.x + 1, bar.y + 1) is None


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
    board_right = theme.board_left + theme.board_size + theme.board_margin
    assert panel.x == board_right
    assert panel.width == theme.panel_width
    assert panel.height == theme.window_height


def test_eval_bar_rect_is_far_left_and_aligned_with_board() -> None:
    theme = DEFAULT_THEME
    layout = BoardLayout(theme, perspective=chess.WHITE)
    bar = layout.eval_bar_rect
    # Pinned to the far left, before the board origin.
    assert bar.x == theme.eval_bar_margin
    assert bar.x + bar.width < theme.board_left
    # Vertically aligned with the board grid.
    assert bar.y == theme.board_margin
    assert bar.height == theme.board_size
    assert bar.width == theme.eval_bar_width


def test_eval_bar_does_not_move_with_perspective() -> None:
    white = BoardLayout(DEFAULT_THEME, perspective=chess.WHITE).eval_bar_rect
    black = BoardLayout(DEFAULT_THEME, perspective=chess.BLACK).eval_bar_rect
    assert (white.x, white.y, white.width, white.height) == (
        black.x,
        black.y,
        black.width,
        black.height,
    )


def test_theme_dimensions_are_consistent() -> None:
    theme = Theme()
    assert theme.board_size == theme.square_size * 8
    assert theme.eval_bar_strip == (
        theme.eval_bar_margin + theme.eval_bar_width + theme.eval_bar_gap
    )
    assert theme.board_left == theme.eval_bar_strip + theme.board_margin
    assert theme.window_width == (
        theme.eval_bar_strip + theme.board_size + theme.board_margin * 2 + theme.panel_width
    )
    assert theme.window_height == theme.board_size + theme.board_margin * 2


def test_eval_fill_fraction_even_and_default() -> None:
    assert eval_fill_fraction(0, None) == 0.5
    # No evaluation yet -> neutral half-and-half.
    assert eval_fill_fraction(None, None) == 0.5


def test_eval_fill_fraction_sign_and_monotonic() -> None:
    white_up = eval_fill_fraction(300, None)
    black_up = eval_fill_fraction(-300, None)
    assert white_up > 0.5 > black_up
    # Symmetric about the midpoint.
    assert abs((white_up - 0.5) - (0.5 - black_up)) < 1e-9
    # Larger advantage -> more fill, but never saturates for cp scores.
    assert eval_fill_fraction(900, None) > white_up
    assert eval_fill_fraction(5000, None) < 1.0


def test_eval_fill_fraction_mate_pins_the_bar() -> None:
    assert eval_fill_fraction(None, 3) == 1.0  # White mates
    assert eval_fill_fraction(None, -2) == 0.0  # White gets mated
    assert eval_fill_fraction(None, 0) == 1.0  # mate "now" -> White
    # Mate dominates any centipawn score that might also be present.
    assert eval_fill_fraction(-800, 1) == 1.0
