"""One live grounded-chat call about a real position. Costs one LLM request.

Uses the same OPENAI_* settings as the app.
Usage: .venv\\Scripts\\python.exe scripts/chat_live.py ["your question"]
"""

from __future__ import annotations

import sys

import chess

from chess_tutor.config import load_settings
from chess_tutor.engine.chess_api import ChessApiProvider
from chess_tutor.explain.chat import PositionChat, build_context, cited_squares
from chess_tutor.explain.review import coach_position

FEN = "r1bq1rk1/pp2bppp/2n1pn2/3p4/3P4/2NB1N2/PP3PPP/R1BQ1RK1 w - - 0 10"  # IQP middlegame


def main() -> None:
    settings = load_settings()
    chat = PositionChat.from_settings(settings)
    if chat is None:
        raise SystemExit("OPENAI_API_KEY is not set in .env")
    print(f"model={settings.openai_model} base={settings.openai_base_url} auth={settings.openai_auth_scheme}")
    question = " ".join(sys.argv[1:]) or "What is the plan for White here, and why?"
    board = chess.Board(FEN)
    analysis = ChessApiProvider(settings.chess_api_ws_url).analyse(
        FEN, multipv=settings.multipv, depth=settings.chess_api_depth
    )
    context = build_context(board, analysis, (), coach_position(board, analysis), chess.WHITE)
    print(context.text, "\n\nQ:", question, "\n")
    answer = chat.ask(context, [], question)
    print("A:", answer)
    print("\ncited squares:", [chess.square_name(s) for s in cited_squares(answer, context)])


if __name__ == "__main__":
    main()
