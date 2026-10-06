"""OpenAI-compatible LLM client: the "brain" that explains and recommends moves.

The LLM never invents moves in a vacuum. It is always *grounded* in the engine's
vetted candidate lines (top-N MultiPV from the :class:`AnalysisProvider`): we hand
it the position plus each candidate's evaluation and principal variation, and ask
it -- in a single call -- to do two things:

1. Recommend exactly one of those candidate moves (the chess engine still has the
   final say; the hybrid core may veto a blunder), and
2. Comment on *every* candidate: why the recommended move is best, and **why not**
   each alternative (its trade-offs).

That comparison -- "why this move, why not that one" -- is the whole point: a learner
improves by understanding the differences between the options, not by being handed a
single move with one blurb. We deliberately keep this to a single LLM round-trip per
position (cost/latency), while still asking for the full comparative explanation.

Design notes
------------
* Prompt building and response parsing are pure functions so they can be unit
  tested without any network access.
* We instruct the model to reply as a small JSON object and parse it leniently
  (tolerating markdown code fences and surrounding prose) rather than relying on
  provider-specific ``response_format`` support, which varies across
  OpenAI-compatible endpoints.
* Transport uses the official ``openai`` SDK pointed at a configurable base URL,
  so any OpenAI-compatible endpoint (Gemini's compat layer, local servers, etc.)
  works unchanged.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings
from .models import Analysis, CandidateLine

_SYSTEM_PROMPT = (
    "You are a strong, encouraging chess coach helping a student improve. You are "
    "given a position and a short list of candidate moves that a chess engine has "
    "already vetted as the best options, each with its evaluation and the principal "
    "variation that follows. Your job is to TEACH by comparison:\n"
    "1. Recommend exactly ONE of the candidate moves.\n"
    "2. Comment on EVERY candidate move in the list: explain why the recommended "
    "move is best, and for each other candidate explain why it is worse -- the "
    "trade-off, the drawback, or what the opponent gets (the 'why not this one?').\n"
    "Base every claim on the evaluations and variations you are given; do not invent "
    "lines or moves that are not listed. Keep each comment concise and instructive.\n"
    "Reply with ONLY a JSON object of this exact shape:\n"
    '{"recommended": "<uci>", "summary": "<one short paragraph on the pick>", '
    '"comparisons": [{"move": "<uci>", "comment": "<why this / why not>"}, ...]}\n'
    "Include one comparisons entry for every candidate you were given, using each "
    "candidate's uci value (for example e2e4 or g8f6)."
)

# Matches a leading ```json / ``` fence and a trailing ``` fence.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_UCI_RE = re.compile(r"\b([a-h][1-8][a-h][1-8][qrbn]?)\b")


class LLMError(RuntimeError):
    """Raised when the LLM cannot be reached or returns an unusable response."""


@dataclass(frozen=True)
class CandidateComment:
    """The LLM's commentary on one candidate move (why this / why not)."""

    move_uci: str
    comment: str


@dataclass(frozen=True)
class MoveProposal:
    """The LLM's grounded, comparative output for a single position.

    Attributes:
        move_uci: The recommended move, in UCI form (lower-cased).
        summary: Overall narrative justifying the recommended move.
        comments: Per-candidate commentary (why this / why not), one entry per
            candidate the LLM addressed, in the order returned.
        grounded: ``True`` when ``move_uci`` matched one of the engine candidates
            that were offered. When ``False``, the hybrid core should treat the
            recommendation with suspicion (and will typically fall back to the
            engine's best move).
        raw: The raw model text, kept for debugging/teaching transparency.
    """

    move_uci: str
    summary: str
    comments: list[CandidateComment] = field(default_factory=list)
    grounded: bool = True
    raw: str | None = None

    def comment_for(self, move_uci: str) -> str | None:
        """Return the LLM's comment for ``move_uci`` (case-insensitive), if any.

        Powers the CLI's "why not <move>?" explainer.
        """
        target = move_uci.strip().lower()
        for c in self.comments:
            if c.move_uci.lower() == target:
                return c.comment
        return None


def side_to_move_name(fen: str) -> str:
    """Return ``"White"`` or ``"Black"`` for the side to move in ``fen``."""
    parts = fen.split()
    return "Black" if len(parts) >= 2 and parts[1] == "b" else "White"


def _format_candidate(line: CandidateLine) -> str:
    """Render a single candidate line as a compact, model-friendly bullet."""
    label = line.move_san or line.move_uci
    pv = " ".join(line.pv[:8]) if line.pv else "(no continuation given)"
    return (
        f"{line.rank}. {label} (uci: {line.move_uci}) "
        f"eval {line.score_text()} | pv: {pv}"
    )


def build_move_prompt(fen: str, analysis: Analysis) -> str:
    """Build the grounded, comparison-oriented prompt from a position + analysis.

    Pure function (no network) so it can be unit tested directly.
    """
    mover = side_to_move_name(fen)
    lines = [_format_candidate(c) for c in analysis.candidates]
    candidates_block = "\n".join(lines) if lines else "(none)"
    depth = f" (search depth {analysis.depth})" if analysis.depth else ""
    return (
        f"Position (FEN): {fen}\n"
        f"Side to move: {mover}\n\n"
        f"Engine-vetted candidate moves{depth}, best first. "
        "Evaluations are in pawns from the mover's perspective "
        "(positive = better for the side to move); #N means mate in N:\n"
        f"{candidates_block}\n\n"
        "Recommend exactly one of the candidate moves above, then comment on EVERY "
        "candidate so the student understands the comparison: why your pick is best "
        "and why each alternative is worse. Use each candidate's uci value. "
        "Respond with only the JSON object described in the system message."
    )


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip())


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of a JSON object from model text."""
    candidate = _strip_fences(text)
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj
    except (TypeError, ValueError):
        pass
    # Fall back to the first {...} span anywhere in the text.
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(candidate[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except (TypeError, ValueError):
            return None
    return None


def _resolve_candidate(token: str, analysis: Analysis) -> CandidateLine | None:
    """Resolve a move token (UCI or SAN, any case) to a vetted candidate."""
    t = token.strip().lower()
    if not t:
        return None
    for c in analysis.candidates:
        if c.move_uci.lower() == t:
            return c
    for c in analysis.candidates:
        if c.move_san and c.move_san.lower() == t:
            return c
    return None


def _parse_comparisons(obj: dict[str, Any], analysis: Analysis) -> list[CandidateComment]:
    """Extract per-candidate comments, normalizing each move to a vetted UCI."""
    raw_items = obj.get("comparisons")
    if not isinstance(raw_items, list):
        return []
    comments: list[CandidateComment] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        move_token = str(item.get("move") or item.get("uci") or "").strip()
        comment = str(item.get("comment") or item.get("reasoning") or "").strip()
        if not comment:
            continue
        match = _resolve_candidate(move_token, analysis)
        move_uci = match.move_uci if match else move_token.lower()
        if not move_uci or move_uci in seen:
            continue
        seen.add(move_uci)
        comments.append(CandidateComment(move_uci=move_uci, comment=comment))
    return comments


def parse_move_response(text: str, analysis: Analysis) -> MoveProposal:
    """Parse the model's reply into a :class:`MoveProposal`, grounded in ``analysis``.

    Lenient by design: tolerates code fences and surrounding prose, normalizes the
    recommended move to a candidate's UCI when possible (matching by UCI or SAN),
    and falls back to scanning for any candidate UCI token. Raises :class:`LLMError`
    only when no recommended move can be recovered at all.
    """
    if not text or not text.strip():
        raise LLMError("LLM returned an empty response.")

    obj = _extract_json_object(text)
    summary = ""
    chosen = ""
    comments: list[CandidateComment] = []
    if obj is not None:
        chosen = str(
            obj.get("recommended") or obj.get("move") or obj.get("uci") or ""
        ).strip()
        summary = str(obj.get("summary") or obj.get("reasoning") or "").strip()
        comments = _parse_comparisons(obj, analysis)

    match = _resolve_candidate(chosen, analysis)

    # If the recommended move didn't resolve, try the first grounded comparison,
    # then scan the whole reply for any candidate UCI token.
    if match is None:
        for c in comments:
            m = _resolve_candidate(c.move_uci, analysis)
            if m is not None:
                match = m
                break
    if match is None:
        valid_uci = {c.move_uci.lower() for c in analysis.candidates}
        for token in _UCI_RE.findall(text.lower()):
            if token in valid_uci:
                match = _resolve_candidate(token, analysis)
                break

    if match is not None:
        if not summary:
            summary = match.comment if False else text.strip()  # keep raw as fallback
        return MoveProposal(
            move_uci=match.move_uci,
            summary=summary,
            comments=comments,
            grounded=True,
            raw=text,
        )

    # Nothing matched a candidate. Keep whatever recommendation string we found (if
    # any) and flag it ungrounded so the hybrid core can veto / fall back.
    if chosen:
        return MoveProposal(
            move_uci=chosen.lower(),
            summary=summary or text.strip(),
            comments=comments,
            grounded=False,
            raw=text,
        )

    raise LLMError("Could not extract a recommended move from the LLM response.")


class LLMClient:
    """Thin wrapper over an OpenAI-compatible chat endpoint for move coaching.

    The transport ``client`` can be injected (any object exposing
    ``chat.completions.create``) which keeps this class unit-testable without a
    real network call. When omitted, a real ``openai.OpenAI`` client is built from
    the supplied credentials.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.2,
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        if client is not None:
            self._client = client
        else:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - import guard
                raise LLMError(
                    "The 'openai' package is required for the LLM client."
                ) from exc
            self._client = OpenAI(api_key=api_key, base_url=base_url)

    @classmethod
    def from_settings(cls, settings: Settings, *, client: Any | None = None) -> LLMClient:
        """Build a client from :class:`Settings`.

        Raises :class:`LLMError` when no API key is configured.
        """
        if not settings.has_llm or not settings.openai_api_key:
            raise LLMError(
                "No LLM API key configured (set OPENAI_API_KEY). "
                "The app can still run engine-only without this client."
            )
        return cls(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            client=client,
        )

    def propose_move(self, fen: str, analysis: Analysis) -> MoveProposal:
        """Make one grounded LLM call and return a recommendation + comparisons.

        A single round-trip yields the recommended move, an overall summary, and a
        "why this / why not" comment for each candidate. Raises :class:`LLMError`
        on transport failure or an unusable response.
        """
        if not analysis.candidates:
            raise LLMError("Cannot propose a move: analysis has no candidates.")

        prompt = build_move_prompt(fen, analysis)
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )
        except Exception as exc:  # noqa: BLE001 - normalize SDK/transport errors
            raise LLMError(f"LLM request failed: {exc}") from exc

        try:
            text = response.choices[0].message.content or ""
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMError("LLM response had no message content.") from exc

        return parse_move_response(text, analysis)
