"""Ad-hoc smoke test: full hybrid pipeline (engine + LLM coaching) on one position.

Run with: python -m uv run python smoke_hybrid.py
Uses .env for OPENAI_* + CHESS_API_* settings. Safe to delete afterwards.
"""

from __future__ import annotations

import chess

from chess_tutor.config import load_settings
from chess_tutor.engine.chess_api import ChessApiProvider
from chess_tutor.engine.hybrid import HybridEngine
from chess_tutor.engine.teaching import comparison_rows, why_not_move, why_this_move


def main() -> None:
    settings = load_settings()
    print(f"LLM configured: {settings.has_llm} | model: {settings.openai_model}")
    print(f"Engine: {settings.chess_api_ws_url} depth={settings.chess_api_depth} "
          f"multipv={settings.multipv} blunder={settings.blunder_threshold_cp}cp\n")

    board = chess.Board()
    provider = ChessApiProvider(settings.chess_api_ws_url)
    engine = HybridEngine.from_settings(settings, provider)
    print(f"HybridEngine.has_llm = {engine.has_llm}\n")

    decision = engine.select_move(board.fen())
    print(f"==> Tutor plays: {decision.move_uci}  [{decision.source}] "
          f"(vetoed={decision.vetoed}, loss={decision.loss_cp}cp)\n")

    print("Candidate comparison:")
    for r in comparison_rows(
        decision.analysis, proposal=decision.proposal, chosen_uci=decision.move_uci
    ):
        star = " *" if r.is_best else "  "
        played = " <= played" if r.is_chosen else ""
        print(f"  {r.rank}.{star} {r.move:5} {r.score:>7} loss=-{r.loss_cp:<4} "
              f"pv={r.pv}{played}")
        if r.comment:
            print(f"        note: {r.comment}")

    print("\nWhy this move:")
    print(f"  {why_this_move(decision)}")

    # Demonstrate the "why not <X>?" explainer on the 2nd candidate, if present.
    if len(decision.analysis.candidates) > 1:
        alt = decision.analysis.candidates[1].move_uci
        print(f"\nWhy not {alt}?")
        print(f"  {why_not_move(decision.analysis, alt, proposal=decision.proposal)}")

    engine.close()
    print("\nSmoke test complete.")


if __name__ == "__main__":
    main()
