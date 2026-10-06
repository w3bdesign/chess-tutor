"""Unit tests for engine data models (provider-agnostic)."""

from __future__ import annotations

from chess_tutor.engine.models import Analysis, CandidateLine


class TestCandidateLineScoreText:
    def test_positive_centipawns(self) -> None:
        line = CandidateLine(move_uci="e2e4", score_cp=135)
        assert line.score_text() == "+1.35"

    def test_negative_centipawns(self) -> None:
        line = CandidateLine(move_uci="e2e4", score_cp=-42)
        assert line.score_text() == "-0.42"

    def test_zero_centipawns(self) -> None:
        line = CandidateLine(move_uci="e2e4", score_cp=0)
        assert line.score_text() == "+0.00"

    def test_mate_for_side_to_move(self) -> None:
        line = CandidateLine(move_uci="e2e4", mate=3)
        assert line.score_text() == "#3"

    def test_mate_against_side_to_move(self) -> None:
        line = CandidateLine(move_uci="e2e4", mate=-2)
        assert line.score_text() == "#-2"

    def test_mate_in_zero(self) -> None:
        line = CandidateLine(move_uci="e2e4", mate=0)
        assert line.score_text() == "#0"

    def test_unknown_score(self) -> None:
        line = CandidateLine(move_uci="e2e4")
        assert line.score_text() == "?"


class TestCandidateLineIsMate:
    def test_is_mate_true(self) -> None:
        assert CandidateLine(move_uci="e2e4", mate=1).is_mate is True

    def test_is_mate_false(self) -> None:
        assert CandidateLine(move_uci="e2e4", score_cp=50).is_mate is False


class TestCandidateLineSortKey:
    def test_higher_cp_sorts_better(self) -> None:
        better = CandidateLine(move_uci="a", score_cp=200)
        worse = CandidateLine(move_uci="b", score_cp=50)
        assert better.sort_key() > worse.sort_key()

    def test_delivering_mate_beats_any_cp(self) -> None:
        mate = CandidateLine(move_uci="a", mate=5)
        huge_cp = CandidateLine(move_uci="b", score_cp=5000)
        assert mate.sort_key() > huge_cp.sort_key()

    def test_faster_mate_beats_slower_mate(self) -> None:
        fast = CandidateLine(move_uci="a", mate=1)
        slow = CandidateLine(move_uci="b", mate=5)
        assert fast.sort_key() > slow.sort_key()

    def test_getting_mated_is_worse_than_any_cp(self) -> None:
        mated = CandidateLine(move_uci="a", mate=-3)
        bad_cp = CandidateLine(move_uci="b", score_cp=-5000)
        assert mated.sort_key() < bad_cp.sort_key()

    def test_later_mate_against_is_less_bad(self) -> None:
        # Getting mated later (-5) is preferable to getting mated sooner (-1).
        later = CandidateLine(move_uci="a", mate=-5)
        sooner = CandidateLine(move_uci="b", mate=-1)
        assert later.sort_key() > sooner.sort_key()

    def test_full_ordering_best_first(self) -> None:
        lines = [
            CandidateLine(move_uci="mated_soon", mate=-1),
            CandidateLine(move_uci="even", score_cp=0),
            CandidateLine(move_uci="winning", score_cp=300),
            CandidateLine(move_uci="mate_in_2", mate=2),
            CandidateLine(move_uci="losing", score_cp=-300),
        ]
        ordered = sorted(lines, key=CandidateLine.sort_key, reverse=True)
        assert [line.move_uci for line in ordered] == [
            "mate_in_2",
            "winning",
            "even",
            "losing",
            "mated_soon",
        ]


class TestAnalysis:
    def test_best_returns_first_candidate(self) -> None:
        first = CandidateLine(move_uci="e2e4", score_cp=50, rank=1)
        second = CandidateLine(move_uci="d2d4", score_cp=30, rank=2)
        analysis = Analysis(fen="startpos", candidates=[first, second])
        assert analysis.best is first

    def test_best_none_when_empty(self) -> None:
        analysis = Analysis(fen="startpos", candidates=[])
        assert analysis.best is None

    def test_find_existing_move(self) -> None:
        target = CandidateLine(move_uci="d2d4", score_cp=30)
        analysis = Analysis(
            fen="startpos",
            candidates=[CandidateLine(move_uci="e2e4", score_cp=50), target],
        )
        assert analysis.find("d2d4") is target

    def test_find_missing_move_returns_none(self) -> None:
        analysis = Analysis(
            fen="startpos",
            candidates=[CandidateLine(move_uci="e2e4", score_cp=50)],
        )
        assert analysis.find("h2h4") is None
