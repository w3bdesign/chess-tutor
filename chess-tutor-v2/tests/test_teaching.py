"""Unit tests for the teaching layer (comparison table + why-this / why-not)."""

from __future__ import annotations

from chess_tutor.engine.hybrid import SOURCE_ENGINE_VETO, SOURCE_LLM, MoveDecision
from chess_tutor.engine.llm import CandidateComment, MoveProposal
from chess_tutor.engine.models import Analysis, CandidateLine
from chess_tutor.engine.teaching import (
    comparison_rows,
    why_not_move,
    why_this_move,
)


def _analysis() -> Analysis:
    return Analysis(
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        candidates=[
            CandidateLine(
                move_uci="e2e4", move_san="e4", score_cp=30, pv=["e2e4", "e7e5"], rank=1
            ),
            CandidateLine(
                move_uci="d2d4", move_san="d4", score_cp=20, pv=["d2d4", "d7d5"], rank=2
            ),
            CandidateLine(move_uci="g1f3", move_san="Nf3", score_cp=-80, rank=3),
        ],
        depth=13,
    )


def _proposal() -> MoveProposal:
    return MoveProposal(
        move_uci="e2e4",
        summary="e4 grabs the center.",
        comments=[
            CandidateComment(move_uci="e2e4", comment="Classic central control."),
            CandidateComment(move_uci="d2d4", comment="Also fine but more closed."),
        ],
    )


class TestComparisonRows:
    def test_one_row_per_candidate(self) -> None:
        rows = comparison_rows(_analysis())
        assert len(rows) == 3

    def test_best_flagged_with_zero_loss(self) -> None:
        rows = comparison_rows(_analysis())
        assert rows[0].is_best is True
        assert rows[0].loss_cp == 0

    def test_loss_relative_to_best(self) -> None:
        rows = comparison_rows(_analysis())
        assert rows[1].loss_cp == 10
        assert rows[2].loss_cp == 110

    def test_chosen_flag(self) -> None:
        rows = comparison_rows(_analysis(), chosen_uci="d2d4")
        chosen = [r for r in rows if r.is_chosen]
        assert len(chosen) == 1
        assert chosen[0].move_uci == "d2d4"

    def test_comment_attached_from_proposal(self) -> None:
        rows = comparison_rows(_analysis(), proposal=_proposal())
        assert rows[0].comment == "Classic central control."
        assert rows[2].comment == ""  # no comment for Nf3

    def test_pv_rendered_in_san_for_replay(self) -> None:
        rows = comparison_rows(_analysis())
        # The raw UCI PV is still available, and a SAN version is derived so a
        # learner can replay the variation on a board.
        assert rows[0].pv == "e2e4 e7e5"
        assert rows[0].pv_san == "e4 e5"

    def test_pv_san_empty_when_no_variation(self) -> None:
        rows = comparison_rows(_analysis())
        assert rows[2].pv_san == ""  # Nf3 line has no stored PV

    def test_empty_analysis_returns_no_rows(self) -> None:
        empty = Analysis(fen="x", candidates=[])
        assert comparison_rows(empty) == []

    def test_san_preferred_as_label(self) -> None:
        rows = comparison_rows(_analysis())
        assert rows[0].move == "e4"


class TestWhyThisMove:
    def _decision(self, **kw: object) -> MoveDecision:
        base: dict[str, object] = {
            "move_uci": "e2e4",
            "source": SOURCE_LLM,
            "vetoed": False,
            "reason": "The coach agrees with the engine: e2e4 is best.",
            "loss_cp": 0,
            "analysis": _analysis(),
            "proposal": _proposal(),
        }
        base.update(kw)
        return MoveDecision(**base)  # type: ignore[arg-type]

    def test_includes_llm_comment(self) -> None:
        text = why_this_move(self._decision())
        assert "Classic central control." in text

    def test_includes_engine_eval(self) -> None:
        text = why_this_move(self._decision())
        assert "+0.30" in text

    def test_includes_decision_reason(self) -> None:
        text = why_this_move(self._decision())
        assert "agrees with the engine" in text

    def test_falls_back_to_summary_when_no_specific_comment(self) -> None:
        proposal = MoveProposal(move_uci="g1f3", summary="Developing move.", comments=[])
        decision = self._decision(move_uci="g1f3", proposal=proposal)
        text = why_this_move(decision)
        assert "Developing move." in text

    def test_engine_only_has_no_llm_text(self) -> None:
        decision = self._decision(
            proposal=None,
            source="engine-only",
            reason="No LLM configured; playing the engine's best move e2e4.",
        )
        text = why_this_move(decision)
        assert "No LLM configured" in text
        assert "+0.30" in text

    def test_veto_reason_surfaced(self) -> None:
        decision = self._decision(
            move_uci="e2e4",
            source=SOURCE_ENGINE_VETO,
            vetoed=True,
            reason="Vetoed the coach's g1f3: ... The engine has the final say.",
        )
        text = why_this_move(decision)
        assert "final say" in text.lower()


class TestWhyNotMove:
    def test_explains_centipawn_gap(self) -> None:
        text = why_not_move(_analysis(), "d2d4")
        assert "10 centipawns" in text
        assert "e4" in text  # names the best move

    def test_accepts_uci(self) -> None:
        text = why_not_move(_analysis(), "g1f3")
        assert "110 centipawns" in text

    def test_best_move_said_to_be_best(self) -> None:
        text = why_not_move(_analysis(), "e4")
        assert "top choice" in text.lower()

    def test_unknown_move_explained(self) -> None:
        text = why_not_move(_analysis(), "a2a3")
        assert "not among" in text.lower()

    def test_layers_in_llm_comment(self) -> None:
        text = why_not_move(_analysis(), "d2d4", proposal=_proposal())
        assert "more closed" in text

    def test_no_analysis(self) -> None:
        empty = Analysis(fen="x", candidates=[])
        assert "no analysis" in why_not_move(empty, "e4").lower()
