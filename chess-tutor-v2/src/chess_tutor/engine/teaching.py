"""Teaching layer: turn engine analysis + the LLM proposal into coaching output.

This module is deliberately **presentation-agnostic**. It returns plain data
(rows, strings) rather than Rich objects, so:

* the logic is trivially unit-testable without a terminal, and
* a future FastAPI/MCP surface can reuse the exact same coaching content.

Three pieces of coaching are produced, all grounded in the engine evaluation:

* a **candidate-move comparison table** (every vetted option, best-first),
* a **why-this-move narrative** for the move actually chosen, and
* a **why-not-<move> explainer** for any specific alternative the student asks
  about.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from .hybrid import MoveDecision, centipawn_loss
from .llm import MoveProposal
from .models import Analysis, CandidateLine


@dataclass(frozen=True)
class ComparisonRow:
    """One row of the candidate-move comparison table."""

    rank: int
    move: str  # SAN when known, else UCI
    move_uci: str
    score: str  # human-readable eval, e.g. "+0.35" or "#3"
    loss_cp: int  # centipawns behind the engine's best (0 for the best line)
    is_best: bool  # engine's top line
    is_chosen: bool  # the move actually played this turn
    pv: str  # short principal variation (space-separated UCI)
    pv_san: str  # same variation rendered in SAN, for replaying on a board
    comment: str  # LLM's why-this/why-not note, if available


def _move_label(line: CandidateLine) -> str:
    return line.move_san or line.move_uci


def _pv_text(line: CandidateLine, *, limit: int = 6) -> str:
    return " ".join(line.pv[:limit]) if line.pv else ""


def _pv_san_text(fen: str, line: CandidateLine, *, limit: int = 6) -> str:
    """Render the principal variation in SAN so a learner can replay it.

    Falls back to the raw UCI (via :func:`_pv_text`) if any move in the stored PV
    is illegal for the position -- providers very occasionally emit a truncated or
    off-by-one PV, and coaching output must never crash the UI over it.
    """
    if not line.pv:
        return ""
    try:
        board = chess.Board(fen)
    except ValueError:
        return _pv_text(line, limit=limit)
    sans: list[str] = []
    for uci in line.pv[:limit]:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break
        if move not in board.legal_moves:
            break
        sans.append(board.san(move))
        board.push(move)
    return " ".join(sans) if sans else _pv_text(line, limit=limit)


def comparison_rows(
    analysis: Analysis,
    *,
    proposal: MoveProposal | None = None,
    chosen_uci: str | None = None,
) -> list[ComparisonRow]:
    """Build comparison rows for every candidate, best-first.

    ``loss_cp`` is each line's centipawn gap behind the engine's best move, which
    is what makes the trade-offs between options concrete for the learner.
    """
    best = analysis.best
    if best is None:
        return []

    rows: list[ComparisonRow] = []
    for line in analysis.candidates:
        comment = proposal.comment_for(line.move_uci) if proposal else None
        rows.append(
            ComparisonRow(
                rank=line.rank,
                move=_move_label(line),
                move_uci=line.move_uci,
                score=line.score_text(),
                loss_cp=max(0, centipawn_loss(best, line)),
                is_best=(line.move_uci == best.move_uci),
                is_chosen=(chosen_uci is not None and line.move_uci == chosen_uci),
                pv=_pv_text(line),
                pv_san=_pv_san_text(analysis.fen, line),
                comment=comment or "",
            )
        )
    return rows


def why_this_move(decision: MoveDecision) -> str:
    """Narrative explaining the move the tutor actually played.

    Combines the engine's authoritative verdict (the decision reason) with the
    LLM's coaching prose when available. Always returns something useful, even in
    engine-only mode.
    """
    parts: list[str] = []
    line = decision.chosen_line
    label = line.move_san if (line and line.move_san) else decision.move_uci

    # Prefer the LLM's own words about the chosen move, then its overall summary.
    if decision.proposal is not None:
        specific = decision.proposal.comment_for(decision.move_uci)
        if specific:
            parts.append(specific)
        elif decision.proposal.summary:
            parts.append(decision.proposal.summary)

    if line is not None:
        parts.append(f"Engine evaluation after {label}: {line.score_text()}.")

    # The decision reason captures agreement / veto / fallback transparently.
    if decision.reason:
        parts.append(decision.reason)

    if not parts:
        parts.append(f"Playing {label}.")
    return " ".join(parts)


def why_not_move(
    analysis: Analysis,
    move: str,
    *,
    proposal: MoveProposal | None = None,
) -> str:
    """Explain why an alternative ``move`` (UCI or SAN) is not the top choice.

    Grounded in the engine eval: reports how many centipawns the alternative
    trails the best move by, and layers in the LLM's comment when present. If the
    move is the engine's best, it says so.
    """
    best = analysis.best
    if best is None:
        return "There is no analysis available for this position."

    line = _find(analysis, move)
    if line is None:
        return (
            f"'{move}' is not among the engine's top {len(analysis.candidates)} "
            "candidate moves for this position, so there is no coached comparison "
            "for it. The engine only evaluated the strongest replies."
        )

    label = line.move_san or line.move_uci
    if line.move_uci == best.move_uci:
        return f"{label} *is* the engine's top choice ({line.score_text()})."

    loss = max(0, centipawn_loss(best, line))
    best_label = best.move_san or best.move_uci
    base = (
        f"{label} evaluates to {line.score_text()}, which trails the engine's best "
        f"move {best_label} ({best.score_text()}) by {loss} centipawns."
    )
    comment = proposal.comment_for(line.move_uci) if proposal else None
    if comment:
        return f"{base} {comment}"
    if line.pv:
        return f"{base} Expected continuation: {_pv_text(line)}."
    return base


def _find(analysis: Analysis, move: str) -> CandidateLine | None:
    """Resolve ``move`` (UCI or SAN, any case) to a candidate line."""
    token = move.strip().lower()
    if not token:
        return None
    for line in analysis.candidates:
        if line.move_uci.lower() == token:
            return line
    for line in analysis.candidates:
        if line.move_san and line.move_san.lower() == token:
            return line
    return None
