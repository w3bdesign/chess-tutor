"""Print the deterministic explanations for a few positions (quick visual check).

Usage: .venv\\Scripts\\python.exe scripts/explain_demo.py
"""

from __future__ import annotations

import chess

from chess_tutor.engine.models import Analysis, CandidateLine
from chess_tutor.explain.imbalances import extract, plan_ideas
from chess_tutor.explain.review import coach_position, review_move


def show_review(fen: str, uci: str, before: Analysis | None) -> None:
    board = chess.Board(fen)
    r = review_move(board, chess.Move.from_uci(uci), before, None)
    print(f"== {r.title}  ({r.eval_text})")
    for p in r.points:
        print("  -", p)
    if r.problem:
        print("  PROBLEM:", r.problem)
    if r.better:
        print("  BETTER:", r.better)
    print("  terms:", ", ".join(r.terms))


def show_position(fen: str) -> None:
    board = chess.Board(fen)
    facts = extract(board)
    print("== Imbalances:", fen)
    for f in facts:
        print(f"  [{f.category}] {f.text}")
    for color in chess.COLORS:
        ideas = plan_ideas(board, facts, color)
        print(f"  Plans for {'White' if color else 'Black'}:")
        for text, _ in ideas:
            print("    *", text)


def line(uci, cp=None, mate=None, pv=(), rank=1):
    return CandidateLine(move_uci=uci, score_cp=cp, mate=mate, pv=list(pv), rank=rank)


if __name__ == "__main__":
    # Blunder: queen walks into capture.
    fen = "3qk3/8/8/8/8/8/8/3QK3 w - - 0 1"
    show_review(fen, "d1d5", Analysis(fen, [line("d1d2", 0, pv=["d1d2"]), line("d1d5", -900, pv=["d1d5", "d8d5"], rank=2)]))
    # Knight fork.
    show_review("r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1", "b5c7", None)
    # Ruy Lopez exchange: Bxc6 gives up the bishop pair.
    fen = "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4"
    show_review(fen, "b5c6", Analysis(fen, [line("e1g1", 30, pv=["e1g1"]), line("b5c6", 10, pv=["b5c6", "d7c6", "e1g1"], rank=2)]))
    # Opening development.
    show_review(chess.STARTING_FEN, "g1f3", None)
    # A middlegame structure (IQP, open files).
    show_position("r1bq1rk1/pp2bppp/2n1pn2/3p4/3P4/2NB1N2/PP3PPP/R1BQ1RK1 w - - 0 10")
    show_position("4k3/pp3ppp/3p4/3N4/4P3/8/PP3PPP/3RK3 w - - 0 25")
    # Coaching with a loose piece.
    fen = "4k3/8/p7/1B6/8/8/8/4K3 w - - 0 1"
    c = coach_position(chess.Board(fen), Analysis(fen, [line("b5c4", 200, pv=["b5c4", "e8d7"])]))
    print("== Coach:", c.eval_text, c.warnings, c.best_text, c.plans)
