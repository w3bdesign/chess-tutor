"""Review every move of a short game with the real engine (chess-api.com), print the text.

Usage: .venv\\Scripts\\python.exe scripts/review_live.py [uci moves...]
Default game: 1.e4 e5 2.Nf3 Nc6 3.Bc4 Nd4? 4.Nxe5? Qg5 5.Nxf7?? Qxg2 (a classic trap).
"""

from __future__ import annotations

import sys

import chess

from chess_tutor.config import load_settings
from chess_tutor.engine.chess_api import ChessApiProvider
from chess_tutor.explain.review import coach_position, review_move

DEFAULT = "e2e4 e7e5 g1f3 b8c6 f1c4 c6d4 f3e5 d8g5 e5f7 g5g2".split()


def main() -> None:
    settings = load_settings()
    provider = ChessApiProvider(settings.chess_api_ws_url)
    moves = sys.argv[1:] or DEFAULT
    board = chess.Board()
    cache: dict[str, object] = {}

    def analyse(fen: str):
        if fen not in cache:
            cache[fen] = provider.analyse(fen, multipv=settings.multipv, depth=settings.chess_api_depth)
        return cache[fen]

    for uci in moves:
        move = chess.Move.from_uci(uci)
        before = board.copy(stack=False)
        after = before.copy(stack=False)
        after.push(move)
        r = review_move(before, move, analyse(before.fen()), None if after.is_game_over() else analyse(after.fen()))
        print(f"\n== {r.title}   [{r.eval_text}]")
        for p in r.points:
            print("   ", p)
        if r.problem:
            print("    PROBLEM:", r.problem)
        if r.better:
            print("    BETTER:", r.better)
        board.push(move)
    c = coach_position(board, analyse(board.fen()))
    print("\n== Coaching for the side to move:", c.eval_text)
    for w in c.warnings:
        print("    !", w)
    print("   ", c.best_text)
    for p in c.plans:
        print("    *", p)


if __name__ == "__main__":
    main()
