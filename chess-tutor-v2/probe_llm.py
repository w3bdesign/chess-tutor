"""Ad-hoc probe: surface the real LLM error (bypasses hybrid's silent catch).

Run with: python -m uv run python probe_llm.py
Safe to delete afterwards.
"""

from __future__ import annotations

import traceback

import chess

from chess_tutor.config import load_settings
from chess_tutor.engine.chess_api import ChessApiProvider
from chess_tutor.engine.llm import LLMClient


def main() -> None:
    settings = load_settings()
    print(f"base_url = {settings.openai_base_url}")
    print(f"model    = {settings.openai_model}")
    print(f"has_llm  = {settings.has_llm}")

    fen = chess.Board().fen()
    provider = ChessApiProvider(settings.chess_api_ws_url)
    analysis = provider.analyse(
        fen, multipv=settings.multipv, depth=settings.chess_api_depth
    )
    print(f"analysis candidates = {[c.move_uci for c in analysis.candidates]}")

    llm = LLMClient.from_settings(settings)
    try:
        proposal = llm.propose_move(fen, analysis)
        print("\n=== PROPOSAL OK ===")
        print(f"move_uci = {proposal.move_uci}")
        print(f"grounded = {proposal.grounded}")
        print(f"summary  = {proposal.summary}")
        print(f"comments = {proposal.comments}")
        print(f"\nraw:\n{proposal.raw}")
    except Exception:  # noqa: BLE001 - probe wants the full traceback
        print("\n=== PROPOSAL FAILED ===")
        traceback.print_exc()
    finally:
        provider.close()


if __name__ == "__main__":
    main()
