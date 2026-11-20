"""Grounded chat about the current position (LLM, on demand only).

The LLM never reads the board on its own. It gets a numbered list of *verified*
facts - Stockfish lines, move reviews, Silman imbalances, warnings - each with an
ID like ``[F3]``. It must cite the IDs it uses and must say when the facts don't
cover a question. Cited IDs map back to squares so the GUI can highlight them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import chess

from ..engine.models import Analysis
from .imbalances import color_name, extract, plan_ideas
from .review import (
    MoveReview,
    PositionCoaching,
    _continuation,
    _line_text,
    eval_words,
    line_cp,
    resolve_line,
)

SYSTEM_PROMPT = """You are a friendly chess coach for a club player rated about 1600.
You explain in the spirit of Jeremy Silman's "How to Reassess Your Chess":
imbalances first, then a plan that uses them.

STRICT RULES
- You can NOT see the board. Use ONLY the numbered facts provided. Every chess
  claim you make must cite at least one fact ID in square brackets, e.g. [F3].
- Never invent moves, tactics, threats or evaluations that are not in the facts.
  Engine lines [E1], [E2]... are the only source of concrete moves.
- If the facts do not answer the question, say so plainly ("The computed facts
  don't cover that") and suggest what the player could check on the board.
- Explain any chess term you use in a few words. Be concise: at most ~150 words,
  short paragraphs or bullets. No preamble."""

_ID_RE = re.compile(r"\[([EF]\d+)\]")


@dataclass
class ChatContext:
    """The fact sheet sent to the LLM plus the squares behind each fact ID."""

    text: str
    squares: dict[str, tuple[chess.Square, ...]] = field(default_factory=dict)


def build_context(
    board: chess.Board,
    analysis: Analysis | None,
    reviews: tuple[MoveReview, ...],
    coaching: PositionCoaching | None,
    human: chess.Color,
) -> ChatContext:
    lines: list[str] = []
    squares: dict[str, tuple[chess.Square, ...]] = {}
    me, them = color_name(human), color_name(not human)
    lines.append(f"Player: {me}. Opponent: {them}. {color_name(board.turn)} to move.")
    lines.append(f"FEN: {board.fen()}")

    # Engine lines.
    if analysis is not None and analysis.candidates:
        best = analysis.best
        cp = line_cp(best) if best else None
        white_cp = None if cp is None else (cp if board.turn == chess.WHITE else -cp)
        lines.append(f"Engine evaluation: {eval_words(white_cp)}.")
        lines.append("ENGINE LINES (best first):")
        for i, cand in enumerate(analysis.candidates[:3], start=1):
            pv = _continuation(cand)
            _d, sans, _ = resolve_line(board, pv, board.turn, max_plies=6)
            text = _line_text(board, sans) if sans else cand.move_uci
            lines.append(f"[E{i}] {text}  (score {cand.score_text()} for the side to move)")
            try:
                m = chess.Move.from_uci(cand.move_uci)
                squares[f"E{i}"] = (m.from_square, m.to_square)
            except ValueError:
                pass

    facts: list[tuple[str, tuple[chess.Square, ...]]] = []
    for review in reviews:
        who = "Player" if review.color == human else "Opponent"
        head = f"{who}'s last move {review.number}{review.san} was rated {review.label or 'unrated'}"
        facts.append((f"{head}; after it {review.eval_text}.", review.marks))
        for p in review.points:
            if p.endswith(":"):
                continue
            facts.append((f"About {review.san}: {p.lstrip('+- ')}", review.marks))
        if review.problem:
            facts.append((f"About {review.san}: {review.problem}", review.marks))
        if review.better:
            facts.append((f"About {review.san}: {review.better}", review.marks))
    if coaching is not None:
        for w in coaching.warnings:
            facts.append((f"Warning for the side to move: {w}", coaching.marks))
    imbalance_facts = extract(board)
    for f in imbalance_facts:
        facts.append((f"Imbalance ({f.category}): {f.text}", f.squares))
    for color in (human, not human):
        for text, sqs in plan_ideas(board, imbalance_facts, color):
            facts.append((f"Silman plan idea for {color_name(color)}: {text}", sqs))

    lines.append("VERIFIED FACTS:")
    for i, (text, sqs) in enumerate(facts, start=1):
        lines.append(f"[F{i}] {text}")
        squares[f"F{i}"] = tuple(sqs)
    if not facts:
        lines.append("(no notable facts computed for this position)")
    return ChatContext(text="\n".join(lines), squares=squares)


def cited_squares(answer: str, context: ChatContext) -> tuple[chess.Square, ...]:
    out: list[chess.Square] = []
    for fid in _ID_RE.findall(answer):
        out.extend(context.squares.get(fid, ()))
    return tuple(dict.fromkeys(out))


class ChatError(RuntimeError):
    pass


class PositionChat:
    """Chat with any OpenAI-compatible endpoint (same OPENAI_* settings as the tutor)."""

    def __init__(
        self, *, api_key: str, base_url: str, model: str, auth_scheme: str = "Bearer"
    ) -> None:
        from ..engine.llm import make_openai_client

        self._client = make_openai_client(api_key=api_key, base_url=base_url, auth_scheme=auth_scheme)
        self._model = model

    @classmethod
    def from_settings(cls, settings) -> PositionChat | None:
        if not settings.openai_api_key:
            return None
        return cls(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            auth_scheme=settings.openai_auth_scheme,
        )

    def ask(self, context: ChatContext, history: list[tuple[str, str]], question: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Position facts:\n" + context.text},
            {"role": "assistant", "content": "Understood. I will only use these facts and cite their IDs."},
        ]
        for role, text in history[-8:]:
            messages.append({"role": role, "content": text})
        messages.append({"role": "user", "content": question})
        try:
            resp = self._client.chat.completions.create(model=self._model, messages=messages)
        except Exception as exc:
            raise ChatError(f"LLM request failed: {exc}") from exc
        text = (resp.choices[0].message.content or "").strip() if resp.choices else ""
        if not text:
            raise ChatError("The LLM returned an empty answer.")
        return text
