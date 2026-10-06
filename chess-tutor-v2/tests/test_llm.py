"""Unit tests for the OpenAI-compatible LLM client (no network).

Transport is faked by injecting an object that mimics
``client.chat.completions.create(...)`` so the grounded prompt-building and the
lenient response-parsing can be exercised deterministically.
"""

from __future__ import annotations

import pytest

from chess_tutor.config import Settings
from chess_tutor.engine.llm import (
    LLMClient,
    LLMError,
    MoveProposal,
    build_move_prompt,
    parse_move_response,
    side_to_move_name,
)
from chess_tutor.engine.models import Analysis, CandidateLine

STARTPOS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
BLACK_TO_MOVE = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"


def _analysis(fen: str = STARTPOS) -> Analysis:
    return Analysis(
        fen=fen,
        depth=13,
        candidates=[
            CandidateLine(
                move_uci="e2e4", move_san="e4", score_cp=35, pv=["e2e4", "e7e5"], rank=1
            ),
            CandidateLine(
                move_uci="d2d4", move_san="d4", score_cp=28, pv=["d2d4", "d7d5"], rank=2
            ),
            CandidateLine(
                move_uci="g1f3", move_san="Nf3", score_cp=25, pv=["g1f3"], rank=3
            ),
        ],
    )


# --- Fake transport ---------------------------------------------------------


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content=None, error=None):
        self._content = content
        self._error = error
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, content=None, error=None):
        self.chat = _FakeChat(_FakeCompletions(content=content, error=error))


# --- side_to_move_name ------------------------------------------------------


class TestSideToMoveName:
    def test_white(self):
        assert side_to_move_name(STARTPOS) == "White"

    def test_black(self):
        assert side_to_move_name(BLACK_TO_MOVE) == "Black"

    def test_malformed_defaults_white(self):
        assert side_to_move_name("not-a-fen") == "White"


# --- build_move_prompt ------------------------------------------------------


class TestBuildMovePrompt:
    def test_includes_fen_and_mover(self):
        prompt = build_move_prompt(STARTPOS, _analysis())
        assert STARTPOS in prompt
        assert "Side to move: White" in prompt

    def test_lists_each_candidate_with_uci_and_eval(self):
        prompt = build_move_prompt(STARTPOS, _analysis())
        assert "uci: e2e4" in prompt
        assert "uci: d2d4" in prompt
        assert "uci: g1f3" in prompt
        assert "+0.35" in prompt  # score_text for 35 cp

    def test_includes_depth_when_present(self):
        prompt = build_move_prompt(STARTPOS, _analysis())
        assert "depth 13" in prompt

    def test_black_to_move(self):
        prompt = build_move_prompt(BLACK_TO_MOVE, _analysis(BLACK_TO_MOVE))
        assert "Side to move: Black" in prompt


# --- parse_move_response ----------------------------------------------------


class TestParseMoveResponse:
    def test_plain_json(self):
        text = '{"move": "e2e4", "reasoning": "Controls the center."}'
        proposal = parse_move_response(text, _analysis())
        assert proposal.move_uci == "e2e4"
        assert proposal.reasoning == "Controls the center."
        assert proposal.grounded is True

    def test_json_in_code_fence(self):
        text = '```json\n{"move": "d2d4", "reasoning": "Queen pawn."}\n```'
        proposal = parse_move_response(text, _analysis())
        assert proposal.move_uci == "d2d4"
        assert proposal.grounded is True

    def test_json_with_surrounding_prose(self):
        text = 'Sure! Here is my pick:\n{"move":"g1f3","reasoning":"Develop."} Enjoy.'
        proposal = parse_move_response(text, _analysis())
        assert proposal.move_uci == "g1f3"
        assert proposal.grounded is True

    def test_resolves_san_to_uci(self):
        text = '{"move": "Nf3", "reasoning": "Knight out."}'
        proposal = parse_move_response(text, _analysis())
        assert proposal.move_uci == "g1f3"
        assert proposal.grounded is True

    def test_uppercase_uci_normalized(self):
        text = '{"move": "E2E4", "reasoning": "Center."}'
        proposal = parse_move_response(text, _analysis())
        assert proposal.move_uci == "e2e4"
        assert proposal.grounded is True

    def test_scans_prose_for_uci_when_json_move_invalid(self):
        # move field is junk, but a valid candidate uci appears in the prose.
        text = '{"move": "zzzz", "reasoning": "I like e2e4 for the center."}'
        proposal = parse_move_response(text, _analysis())
        assert proposal.move_uci == "e2e4"
        assert proposal.grounded is True

    def test_ungrounded_move_flagged(self):
        # A legal-looking uci that is NOT among the candidates.
        text = '{"move": "a2a3", "reasoning": "Edge pawn."}'
        proposal = parse_move_response(text, _analysis())
        assert proposal.move_uci == "a2a3"
        assert proposal.grounded is False

    def test_empty_response_raises(self):
        with pytest.raises(LLMError):
            parse_move_response("   ", _analysis())

    def test_no_move_anywhere_raises(self):
        with pytest.raises(LLMError):
            parse_move_response("I have no idea what to play.", _analysis())

    def test_reasoning_falls_back_to_full_text(self):
        # Grounded by prose scan, but no reasoning field -> keep raw text.
        text = "Play e2e4!"
        proposal = parse_move_response(text, _analysis())
        assert proposal.move_uci == "e2e4"
        assert "e2e4" in proposal.reasoning


# --- LLMClient.propose_move -------------------------------------------------


class TestProposeMove:
    def test_happy_path(self):
        client = LLMClient(
            api_key="k",
            base_url="http://x",
            model="m",
            client=_FakeClient('{"move":"e2e4","reasoning":"Center."}'),
        )
        proposal = client.propose_move(STARTPOS, _analysis())
        assert isinstance(proposal, MoveProposal)
        assert proposal.move_uci == "e2e4"
        assert proposal.grounded is True

    def test_passes_model_and_messages(self):
        fake = _FakeClient('{"move":"e2e4","reasoning":"ok"}')
        client = LLMClient(api_key="k", base_url="http://x", model="my-model", client=fake)
        client.propose_move(STARTPOS, _analysis())
        kwargs = fake.chat.completions.last_kwargs
        assert kwargs["model"] == "my-model"
        assert kwargs["messages"][0]["role"] == "system"
        assert kwargs["messages"][1]["role"] == "user"
        assert STARTPOS in kwargs["messages"][1]["content"]

    def test_no_candidates_raises(self):
        client = LLMClient(
            api_key="k", base_url="http://x", model="m", client=_FakeClient("{}")
        )
        empty = Analysis(fen=STARTPOS, candidates=[], depth=None)
        with pytest.raises(LLMError):
            client.propose_move(STARTPOS, empty)

    def test_transport_error_wrapped(self):
        client = LLMClient(
            api_key="k",
            base_url="http://x",
            model="m",
            client=_FakeClient(error=RuntimeError("boom")),
        )
        with pytest.raises(LLMError):
            client.propose_move(STARTPOS, _analysis())

    def test_none_content_raises(self):
        client = LLMClient(
            api_key="k", base_url="http://x", model="m", client=_FakeClient(None)
        )
        with pytest.raises(LLMError):
            client.propose_move(STARTPOS, _analysis())


# --- from_settings ----------------------------------------------------------


def _settings(api_key):
    return Settings(
        openai_api_key=api_key,
        openai_base_url="http://x",
        openai_model="m",
        chess_api_ws_url="wss://chess-api.com/v1",
        chess_api_depth=13,
        multipv=3,
        blunder_threshold_cp=80,
    )


class TestFromSettings:
    def test_requires_api_key(self):
        with pytest.raises(LLMError):
            LLMClient.from_settings(_settings(None), client=_FakeClient("{}"))

    def test_builds_with_injected_client(self):
        client = LLMClient.from_settings(
            _settings("sk-test"), client=_FakeClient('{"move":"e2e4","reasoning":"ok"}')
        )
        proposal = client.propose_move(STARTPOS, _analysis())
        assert proposal.move_uci == "e2e4"
