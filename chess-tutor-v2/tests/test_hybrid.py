"""Unit tests for the hybrid move-selection core (engine has the final say)."""

from __future__ import annotations

from chess_tutor.engine.hybrid import (
    SOURCE_ENGINE_FALLBACK,
    SOURCE_ENGINE_ONLY,
    SOURCE_ENGINE_VETO,
    SOURCE_LLM,
    HybridEngine,
    MoveDecision,
    centipawn_loss,
    evaluate_choice,
)
from chess_tutor.engine.llm import CandidateComment, MoveProposal
from chess_tutor.engine.models import Analysis, CandidateLine
from chess_tutor.engine.provider import AnalysisProvider


def _analysis() -> Analysis:
    return Analysis(
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        candidates=[
            CandidateLine(move_uci="e2e4", move_san="e4", score_cp=30, rank=1),
            CandidateLine(move_uci="d2d4", move_san="d4", score_cp=20, rank=2),
            CandidateLine(move_uci="g1f3", move_san="Nf3", score_cp=-100, rank=3),
        ],
        depth=13,
    )


def _proposal(move_uci: str, *, grounded: bool = True) -> MoveProposal:
    return MoveProposal(
        move_uci=move_uci,
        summary=f"Recommending {move_uci}.",
        comments=[CandidateComment(move_uci=move_uci, comment="because reasons")],
        grounded=grounded,
    )


class TestCentipawnLoss:
    def test_best_has_zero_loss(self) -> None:
        a = _analysis()
        assert centipawn_loss(a.candidates[0], a.candidates[0]) == 0

    def test_second_best_positive_loss(self) -> None:
        a = _analysis()
        assert centipawn_loss(a.candidates[0], a.candidates[1]) == 10

    def test_mate_beats_centipawns(self) -> None:
        best = CandidateLine(move_uci="h7h8q", mate=1, rank=1)
        other = CandidateLine(move_uci="a2a3", score_cp=500, rank=2)
        assert centipawn_loss(best, other) > 0

    def test_faster_mate_preferred(self) -> None:
        mate_in_1 = CandidateLine(move_uci="a", mate=1)
        mate_in_3 = CandidateLine(move_uci="b", mate=3)
        assert centipawn_loss(mate_in_1, mate_in_3) > 0


class TestEvaluateChoice:
    def test_engine_only_when_no_proposal(self) -> None:
        move, source, vetoed, loss, _ = evaluate_choice(
            _analysis(), None, blunder_threshold_cp=80
        )
        assert move == "e2e4"
        assert source == SOURCE_ENGINE_ONLY
        assert vetoed is False
        assert loss == 0

    def test_agreement_with_engine_best(self) -> None:
        move, source, vetoed, loss, _ = evaluate_choice(
            _analysis(), _proposal("e2e4"), blunder_threshold_cp=80
        )
        assert move == "e2e4"
        assert source == SOURCE_LLM
        assert vetoed is False
        assert loss == 0

    def test_accepts_within_threshold(self) -> None:
        move, source, vetoed, loss, _ = evaluate_choice(
            _analysis(), _proposal("d2d4"), blunder_threshold_cp=80
        )
        assert move == "d2d4"
        assert source == SOURCE_LLM
        assert vetoed is False
        assert loss == 10

    def test_vetoes_blunder_over_threshold(self) -> None:
        move, source, vetoed, loss, reason = evaluate_choice(
            _analysis(), _proposal("g1f3"), blunder_threshold_cp=80
        )
        assert move == "e2e4"  # engine best wins
        assert source == SOURCE_ENGINE_VETO
        assert vetoed is True
        assert loss == 130
        assert "final say" in reason.lower()

    def test_fallback_when_move_not_a_candidate(self) -> None:
        move, source, vetoed, _, _ = evaluate_choice(
            _analysis(), _proposal("a2a3"), blunder_threshold_cp=80
        )
        assert move == "e2e4"
        assert source == SOURCE_ENGINE_FALLBACK
        assert vetoed is True

    def test_fallback_when_ungrounded(self) -> None:
        move, source, vetoed, _, _ = evaluate_choice(
            _analysis(), _proposal("d2d4", grounded=False), blunder_threshold_cp=80
        )
        assert move == "e2e4"
        assert source == SOURCE_ENGINE_FALLBACK
        assert vetoed is True

    def test_threshold_boundary_is_inclusive(self) -> None:
        # Loss exactly equal to the threshold is NOT a veto (only strictly greater).
        move, source, _, loss, _ = evaluate_choice(
            _analysis(), _proposal("d2d4"), blunder_threshold_cp=10
        )
        assert loss == 10
        assert move == "d2d4"
        assert source == SOURCE_LLM


class _StubProvider(AnalysisProvider):
    def __init__(self, analysis: Analysis) -> None:
        self._analysis = analysis
        self.closed = False
        self.calls = 0

    def analyse(self, fen: str, *, multipv: int, depth: int) -> Analysis:
        self.calls += 1
        return self._analysis

    def close(self) -> None:
        self.closed = True


class _StubLLM:
    def __init__(self, proposal: MoveProposal | None, *, raise_error: bool = False) -> None:
        self._proposal = proposal
        self._raise = raise_error
        self.calls = 0

    def propose_move(self, fen: str, analysis: Analysis) -> MoveProposal:
        from chess_tutor.engine.llm import LLMError

        self.calls += 1
        if self._raise:
            raise LLMError("boom")
        assert self._proposal is not None
        return self._proposal


class TestHybridEngine:
    def test_engine_only_without_llm(self) -> None:
        provider = _StubProvider(_analysis())
        engine = HybridEngine(provider, llm=None, blunder_threshold_cp=80)
        decision = engine.select_move("fen")
        assert isinstance(decision, MoveDecision)
        assert decision.move_uci == "e2e4"
        assert decision.source == SOURCE_ENGINE_ONLY
        assert engine.has_llm is False

    def test_uses_llm_recommendation(self) -> None:
        provider = _StubProvider(_analysis())
        llm = _StubLLM(_proposal("d2d4"))
        engine = HybridEngine(provider, llm=llm, blunder_threshold_cp=80)  # type: ignore[arg-type]
        decision = engine.select_move("fen")
        assert decision.move_uci == "d2d4"
        assert decision.source == SOURCE_LLM
        assert decision.proposal is not None

    def test_llm_error_degrades_to_engine(self) -> None:
        provider = _StubProvider(_analysis())
        llm = _StubLLM(None, raise_error=True)
        engine = HybridEngine(provider, llm=llm, blunder_threshold_cp=80)  # type: ignore[arg-type]
        decision = engine.select_move("fen")
        assert decision.move_uci == "e2e4"
        assert decision.source == SOURCE_ENGINE_ONLY
        assert decision.proposal is None

    def test_reuses_passed_analysis(self) -> None:
        provider = _StubProvider(_analysis())
        engine = HybridEngine(provider, llm=None)
        pre = engine.analyse("fen")
        assert provider.calls == 1
        engine.select_move("fen", analysis=pre)
        assert provider.calls == 1  # no second analysis call

    def test_close_delegates_to_provider(self) -> None:
        provider = _StubProvider(_analysis())
        engine = HybridEngine(provider, llm=None)
        engine.close()
        assert provider.closed is True

    def test_chosen_line_lookup(self) -> None:
        provider = _StubProvider(_analysis())
        engine = HybridEngine(provider, llm=None)
        decision = engine.select_move("fen")
        assert decision.chosen_line is not None
        assert decision.chosen_line.move_uci == "e2e4"
