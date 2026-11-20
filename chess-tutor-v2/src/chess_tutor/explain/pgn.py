"""PGN import / annotated PGN export for game reviews."""

from __future__ import annotations

import datetime as _dt
import io

import chess
import chess.pgn

from .review import MoveReview

# Lichess-style NAGs for the quality labels.
_NAGS = {
    "Inaccuracy": chess.pgn.NAG_DUBIOUS_MOVE,  # ?!
    "Mistake": chess.pgn.NAG_MISTAKE,  # ?
    "Blunder": chess.pgn.NAG_BLUNDER,  # ??
}


class PgnError(ValueError):
    pass


def load_pgn(text: str) -> tuple[chess.Board, dict[str, str]]:
    """Parse the first game in ``text``; return the final board (with its move stack)
    and the PGN headers."""
    game = chess.pgn.read_game(io.StringIO(text))
    if game is None:
        raise PgnError("No game found in the PGN.")
    if game.errors:
        raise PgnError(f"Could not read the PGN: {game.errors[0]}")
    board = game.board()
    for move in game.mainline_moves():
        board.push(move)
    if not board.move_stack:
        raise PgnError("The PGN contains no moves.")
    return board, dict(game.headers)


def review_comment(review: MoveReview) -> str:
    parts = []
    if review.label:
        parts.append(f"{review.label}.")
    parts.append(review.eval_text[0].upper() + review.eval_text[1:] + ".")
    if review.problem:
        parts.append(review.problem)
    if review.better:
        parts.append(review.better)
    return " ".join(parts)


def export_pgn(
    board: chess.Board,
    reviews: dict[int, MoveReview],
    *,
    white: str = "?",
    black: str = "?",
    event: str = "Chess Tutor game",
    extra_headers: dict[str, str] | None = None,
) -> str:
    """Annotated PGN of ``board``'s game: quality NAGs + review comments per move."""
    game = chess.pgn.Game.from_board(board)
    game.headers["Event"] = event
    game.headers["Site"] = "Chess Tutor v2"
    game.headers["Date"] = _dt.date.today().strftime("%Y.%m.%d")
    game.headers["White"] = white
    game.headers["Black"] = black
    for key, value in (extra_headers or {}).items():
        if key not in ("FEN", "SetUp"):
            game.headers[key] = value
    game.headers["Result"] = board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else (
        (extra_headers or {}).get("Result", "*")
    )
    game.headers["Annotator"] = "Chess Tutor v2 (Stockfish + rule-based explanations)"
    for ply, node in enumerate(game.mainline()):
        review = reviews.get(ply)
        if review is None:
            continue
        nag = _NAGS.get(review.label)
        if nag:
            node.nags.add(nag)
        node.comment = review_comment(review)
    exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
    return game.accept(exporter) + "\n"


def summary(reviews: dict[int, MoveReview]) -> dict[chess.Color, dict[str, int]]:
    """Count inaccuracies / mistakes / blunders per side."""
    out = {c: {"Inaccuracy": 0, "Mistake": 0, "Blunder": 0} for c in chess.COLORS}
    for review in reviews.values():
        if review.label in out[review.color]:
            out[review.color][review.label] += 1
    return out
