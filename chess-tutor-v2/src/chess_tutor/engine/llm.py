"""OpenAI-compatible LLM client: the "brain" that proposes a move + reasoning.

The LLM never invents moves in a vacuum. It is always *grounded* in the engine's
vetted candidate lines (top-N MultiPV from the :class:`AnalysisProvider`): we hand
it the position plus each candidate's evaluation and principal variation, and ask
it to pick exactly one of those moves and explain why. The chess engine still has
the final say -- the hybrid core (see ``core.py``) may veto a blunder -- so the
LLM's job is selection + teaching, not raw calculation.

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
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from .models import Analysis, CandidateLine

_SYSTEM_PROMPT = (
    "You are a strong, encouraging chess coach. You are given a position and a "
    "short list of candidate moves that a chess engine has already vetted as the "
    "best options, each with its evaluation and the principal variation that "
    "follows. Your job is to choose exactly ONE of those candidate moves and "
    "explain, in clear and instructive language, why it is a good practical "
    "choice. Base every claim on the evaluations and variations you are given; "
    "do not invent lines or moves that are not listed. "
    'Reply with ONLY a JSON object of the form '
    '{"move": "<uci>", "reasoning": "<one short paragraph>"}, where <uci> is the '
    "UCI string of the candidate you pick (for example e2e4 or g8f6)."
)

# Matches a leading ```json / ``` fence and a trailing ``` fence.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_UCI_RE = re.compile(r"\b([a-h][1-8][a-h][1-8][qrbn]?)\b")


class LLMError(RuntimeError):
    """Raised when the LLM cannot be reached or returns an unusable response."""


@dataclass(frozen=True)
class MoveProposal:
    """The LLM's grounded suggestion for a single position.

    Attributes:
        move_uci: The move the LLM chose, in UCI form (lower-cased).
        reasoning: The LLM's natural-language justification.
        grounded: ``True`` when ``move_uci`` matched one of the engine candidates
            that were offered. When ``False``, the hybrid core should treat the
            suggestion with suspicion (and will typically fall back to the
            engine's best move).
        raw: The raw model text, kept for debugging/teaching transparency.
    """

    move_uci: str
    reasoning: str
    grounded: bool = True
    raw: str | None = None


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
    """Build the grounded user prompt from a position and its engine analysis.

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
        "Choose exactly one of the candidate moves above (use its uci value) and "
        "explain why it is a good choice for the side to move. "
        'Respond with only the JSON object: {"move": "<uci>", "reasoning": "<text>"}.'
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


def parse_move_response(text: str, analysis: Analysis) -> MoveProposal:
    """Parse the model's reply into a :class:`MoveProposal`, grounded in ``analysis``.

    Lenient by design: tolerates code fences and surrounding prose, normalizes the
    chosen move to a candidate's UCI when possible (matching by UCI or SAN), and
    falls back to scanning for any UCI token. Raises :class:`LLMError` only when no
    move can be recovered at all.
    """
    if not text or not text.strip():
        raise LLMError("LLM returned an empty response.")

    valid_uci = {c.move_uci.lower(): c for c in analysis.candidates}
    valid_san = {
        c.move_san.lower(): c for c in analysis.candidates if c.move_san
    }

    obj = _extract_json_object(text)
    reasoning = ""
    chosen = ""
    if obj is not None:
        chosen = str(obj.get("move") or obj.get("uci") or "").strip()
        reasoning = str(obj.get("reasoning") or obj.get("explanation") or "").strip()

    # Resolve the chosen move against the vetted candidates.
    def _resolve(token: str) -> CandidateLine | None:
        t = token.strip().lower()
        if not t:
            return None
        if t in valid_uci:
            return valid_uci[t]
        if t in valid_san:
            return valid_san[t]
        return None

    match = _resolve(chosen)

    # If the JSON "move" didn't resolve, scan the whole reply for a UCI token
    # that matches a candidate before giving up.
    if match is None:
        for token in _UCI_RE.findall(text.lower()):
            if token in valid_uci:
                match = valid_uci[token]
                break

    if match is not None:
        if not reasoning:
            reasoning = text.strip()
        return MoveProposal(
            move_uci=match.move_uci,
            reasoning=reasoning,
            grounded=True,
            raw=text,
        )

    # Nothing matched a candidate. Keep whatever move string we found (if any)
    # and flag it as ungrounded so the hybrid core can veto / fall back.
    if chosen:
        return MoveProposal(
            move_uci=chosen.lower(),
            reasoning=reasoning or text.strip(),
            grounded=False,
            raw=text,
        )

    raise LLMError("Could not extract a move from the LLM response.")


class LLMClient:
    """Thin wrapper over an OpenAI-compatible chat endpoint for move proposals.

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
        """Make one grounded LLM call and return its chosen move + reasoning.

        Raises :class:`LLMError` on transport failure or an unusable response.
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
