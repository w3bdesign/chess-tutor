"""Hybrid move selection: the LLM proposes, the chess engine has the final say.

This is the heart of the tutor's "play" behaviour. For a given position we:

1. Ask the :class:`AnalysisProvider` (chess engine) for its top-N vetted
   candidate lines.
2. Ask the :class:`LLMClient` (the "brain") to recommend one of those candidates
   and explain the comparison (why this / why not).
3. **Enforce the engine as the authority**: if the LLM's pick is not one of the
   engine's candidates, or it loses more than ``blunder_threshold_cp`` centipawns
   versus the engine's best move, we override it with the engine's best move.

The veto logic is a pure function (:func:`evaluate_choice`) so it can be unit
tested exhaustively without any network, LLM, or engine access.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from .llm import LLMClient, LLMError, MoveProposal
from .models import Analysis, CandidateLine
from .provider import AnalysisProvider

# Centipawn-equivalent anchor for forced mates, so mates always dominate normal
# evaluations when comparing candidate moves. A faster mate scores higher.
_MATE_SCORE = 100_000


def _score_value(line: CandidateLine) -> int:
    """Map a candidate to a single comparable score (side-to-move perspective).

    Larger is better for the side to move. Mates are collapsed onto a very
    large (positive for us / negative against us) scale so they always outrank
    centipawn evaluations, with faster mates beating slower ones.
    """
    if line.mate is not None:
        if line.mate >= 0:
            return _MATE_SCORE - line.mate * 100
        return -_MATE_SCORE - line.mate * 100
    return line.score_cp if line.score_cp is not None else 0


def centipawn_loss(best: CandidateLine, chosen: CandidateLine) -> int:
    """Centipawns lost by playing ``chosen`` instead of the engine's ``best``.

    Always ``>= 0`` when ``best`` really is the top candidate.
    """
    return _score_value(best) - _score_value(chosen)


# Decision sources, for display + testing.
SOURCE_LLM = "llm"  # played the LLM's recommendation
SOURCE_ENGINE_VETO = "engine-veto"  # LLM pick overridden as a blunder
SOURCE_ENGINE_FALLBACK = "engine-fallback"  # LLM pick unusable / unavailable
SOURCE_ENGINE_ONLY = "engine-only"  # no LLM configured at all


@dataclass(frozen=True)
class MoveDecision:
    """The outcome of hybrid move selection for one position.

    Attributes:
        move_uci: The move that will actually be played (engine-authoritative).
        source: One of the ``SOURCE_*`` constants explaining who decided.
        vetoed: ``True`` when the LLM's recommendation was overridden.
        reason: Human-readable explanation of the decision.
        loss_cp: Centipawns the LLM's pick would have lost vs the engine best
            (``0`` when the LLM agreed with the engine or no LLM was used).
        analysis: The engine analysis the decision was based on.
        proposal: The LLM proposal, when an LLM was consulted.
    """

    move_uci: str
    source: str
    vetoed: bool
    reason: str
    loss_cp: int
    analysis: Analysis
    proposal: MoveProposal | None = None

    @property
    def chosen_line(self) -> CandidateLine | None:
        """The candidate line for the move that will be played, if listed."""
        return self.analysis.find(self.move_uci)


def evaluate_choice(
    analysis: Analysis,
    proposal: MoveProposal | None,
    *,
    blunder_threshold_cp: int,
) -> tuple[str, str, bool, int, str]:
    """Decide the final move given engine analysis and an (optional) LLM proposal.

    Pure function. Returns ``(move_uci, source, vetoed, loss_cp, reason)``.

    The engine always has the final say:

    * No proposal (engine-only mode) -> play the engine's best move.
    * Proposal not grounded in / not found among the candidates -> fall back to
      the engine's best move.
    * Proposal loses more than ``blunder_threshold_cp`` vs the best -> veto and
      play the engine's best move.
    * Otherwise -> play the LLM's (engine-vetted) recommendation.
    """
    best = analysis.best
    if best is None:
        raise ValueError("Cannot decide a move from an analysis with no candidates.")

    if proposal is None:
        return (
            best.move_uci,
            SOURCE_ENGINE_ONLY,
            False,
            0,
            f"No LLM configured; playing the engine's best move {best.move_uci}.",
        )

    chosen = analysis.find(proposal.move_uci) if proposal.move_uci else None
    if chosen is None or not proposal.grounded:
        return (
            best.move_uci,
            SOURCE_ENGINE_FALLBACK,
            True,
            0,
            (
                f"The coach's suggestion ({proposal.move_uci or 'none'}) was not among "
                f"the engine's candidates; falling back to the engine's best move "
                f"{best.move_uci}."
            ),
        )

    if chosen.move_uci == best.move_uci:
        return (
            chosen.move_uci,
            SOURCE_LLM,
            False,
            0,
            f"The coach agrees with the engine: {best.move_uci} is best.",
        )

    loss = centipawn_loss(best, chosen)
    if loss > blunder_threshold_cp:
        return (
            best.move_uci,
            SOURCE_ENGINE_VETO,
            True,
            loss,
            (
                f"Vetoed the coach's {chosen.move_uci}: it loses {loss} cp vs the "
                f"engine's best {best.move_uci} (threshold {blunder_threshold_cp} cp). "
                "The engine has the final say."
            ),
        )

    return (
        chosen.move_uci,
        SOURCE_LLM,
        False,
        loss,
        (
            f"Playing the coach's {chosen.move_uci}; it is within "
            f"{blunder_threshold_cp} cp of the engine's best "
            f"(costs {loss} cp)."
        ),
    )


class HybridEngine:
    """Combine an analysis provider and an optional LLM into a move selector.

    When ``llm`` is ``None`` the engine still plays (engine-only), so the tutor
    is usable without an API key -- just without the coaching narrative.
    """

    def __init__(
        self,
        provider: AnalysisProvider,
        *,
        llm: LLMClient | None = None,
        multipv: int = 3,
        depth: int = 13,
        blunder_threshold_cp: int = 80,
    ) -> None:
        self._provider = provider
        self._llm = llm
        self._multipv = multipv
        self._depth = depth
        self._blunder_threshold_cp = blunder_threshold_cp

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        provider: AnalysisProvider,
        *,
        llm: LLMClient | None = None,
    ) -> HybridEngine:
        """Build a :class:`HybridEngine` from :class:`Settings`.

        If ``llm`` is not supplied and a key is configured, one is created from
        settings; otherwise the engine runs engine-only.
        """
        if llm is None and settings.has_llm:
            try:
                llm = LLMClient.from_settings(settings)
            except LLMError:
                llm = None
        return cls(
            provider,
            llm=llm,
            multipv=settings.multipv,
            depth=settings.chess_api_depth,
            blunder_threshold_cp=settings.blunder_threshold_cp,
        )

    @property
    def has_llm(self) -> bool:
        return self._llm is not None

    def analyse(self, fen: str) -> Analysis:
        """Return the engine's analysis for ``fen`` (top-N candidate lines)."""
        return self._provider.analyse(
            fen, multipv=self._multipv, depth=self._depth
        )

    def select_move(self, fen: str, *, analysis: Analysis | None = None) -> MoveDecision:
        """Select the move to play for ``fen`` (engine-authoritative).

        Pass a pre-computed ``analysis`` to reuse an earlier engine call (e.g. a
        hint shown to the player) and avoid a second request.
        """
        if analysis is None:
            analysis = self.analyse(fen)

        proposal: MoveProposal | None = None
        if self._llm is not None:
            try:
                proposal = self._llm.propose_move(fen, analysis)
            except LLMError:
                proposal = None  # degrade to engine-only for this move

        move_uci, source, vetoed, loss, reason = evaluate_choice(
            analysis, proposal, blunder_threshold_cp=self._blunder_threshold_cp
        )
        return MoveDecision(
            move_uci=move_uci,
            source=source,
            vetoed=vetoed,
            reason=reason,
            loss_cp=loss,
            analysis=analysis,
            proposal=proposal,
        )

    def close(self) -> None:
        self._provider.close()
