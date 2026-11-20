"""What is being viewed: pure helpers over the controller (no pygame).

The board and the panel both need "the eval / engine lines / review for the
position currently shown" - which may be an earlier position when browsing.
"""

from __future__ import annotations

from ..engine.teaching import ComparisonRow, comparison_rows
from ..explain.review import MoveReview, PositionCoaching
from .controller import CoachState, GameController, _white_perspective_eval


def view_eval(controller: GameController, state: CoachState) -> tuple[int | None, int | None]:
    """White-perspective ``(cp, mate)`` for the position being shown."""
    analysis = controller.view_analysis()
    if analysis is not None:
        return _white_perspective_eval(analysis)
    if controller.at_latest:
        return state.eval_cp, state.eval_mate
    return None, None


def view_rows(controller: GameController, state: CoachState) -> tuple[ComparisonRow, ...]:
    """Engine candidate rows for the position being shown."""
    if controller.at_latest and not controller.analysis_mode:
        return state.rows
    analysis = controller.view_analysis()
    return tuple(comparison_rows(analysis)) if analysis is not None else ()


def latest_review(controller: GameController) -> MoveReview | None:
    """Review of the move that led to the position being shown, if ready."""
    return controller.review_for(controller.view_len - 1)


def current_coaching(controller: GameController, state: CoachState) -> PositionCoaching | None:
    """Coaching for the human's turn, only when looking at the live position."""
    if (
        controller.at_latest
        and state.coaching is not None
        and state.coaching_fen == controller.board.fen()
    ):
        return state.coaching
    return None
