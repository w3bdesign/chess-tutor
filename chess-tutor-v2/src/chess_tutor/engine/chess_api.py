"""Analysis provider backed by the hosted chess-api.com engine (Stockfish NNUE).

chess-api.com exposes two surfaces:

* an HTTP POST endpoint that returns only a **single** best move, and
* a WebSocket endpoint (``wss://chess-api.com/v1``) that **streams** progress
  messages and, when ``variants`` > 1 is requested, multiple candidate lines
  (MultiPV) as the search deepens.

This provider uses the WebSocket surface so it can surface top-N candidates.
Messages are streamed per depth; for each distinct candidate move we keep the
deepest message seen, then sort best-first and return up to ``multipv`` lines
(degrading gracefully if the engine returns fewer).

Eval normalization
------------------
chess-api.com reports ``eval``/``centipawns``/``mate`` from **White's**
perspective. Our models expect scores from the **side-to-move** perspective, so
we negate when it is Black to move (see :func:`_candidate_from_message`).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets

from .models import Analysis, CandidateLine
from .provider import AnalysisError, AnalysisProvider

# chess-api.com hard limits (documented): variants<=5, depth<=18.
_MAX_VARIANTS = 5
_MAX_DEPTH = 18

# Message ``type`` values that carry a concrete candidate move.
_MOVE_TYPES = {"move", "bestmove"}


def _side_to_move_is_white(fen: str) -> bool:
    """Return True if it is White's turn in ``fen`` (defaults to White)."""
    parts = fen.split()
    return len(parts) < 2 or parts[1] != "b"


def _as_int(value: Any) -> int | None:
    """Best-effort int coercion; returns None when not convertible."""
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _candidate_from_message(
    msg: dict[str, Any], *, white_to_move: bool
) -> CandidateLine | None:
    """Build a :class:`CandidateLine` from one chess-api.com message.

    Scores are normalized from White's perspective to the side-to-move
    perspective. Returns ``None`` when the message carries no usable move.
    """
    move_uci = msg.get("move") or msg.get("from", "") and msg.get("lan")
    move_uci = msg.get("move") or move_uci
    if not move_uci:
        return None

    sign = 1 if white_to_move else -1

    mate = _as_int(msg.get("mate"))
    if mate is not None:
        mate = sign * mate

    score_cp: int | None = None
    if mate is None:
        cp = msg.get("centipawns")
        if cp is None and msg.get("eval") is not None:
            # ``eval`` is in pawns; convert to centipawns.
            try:
                cp = float(msg["eval"]) * 100
            except (TypeError, ValueError):
                cp = None
        score_cp = _as_int(cp)
        if score_cp is not None:
            score_cp = sign * score_cp

    pv = msg.get("continuationArr") or []
    if not isinstance(pv, list):
        pv = []

    return CandidateLine(
        move_uci=str(move_uci),
        move_san=msg.get("san"),
        score_cp=score_cp,
        mate=mate,
        pv=[str(m) for m in pv],
        rank=0,
    )


def _build_analysis(
    fen: str, messages: list[dict[str, Any]], *, multipv: int
) -> Analysis:
    """Aggregate streamed messages into a best-first :class:`Analysis`.

    For each distinct candidate move we keep the message reaching the greatest
    depth, then sort best-first (side-to-move perspective) and keep up to
    ``multipv`` lines. ``rank`` is assigned 1-based after sorting.
    """
    white_to_move = _side_to_move_is_white(fen)

    # Keep the deepest message per distinct move.
    deepest: dict[str, tuple[int, dict[str, Any]]] = {}
    max_depth = 0
    for msg in messages:
        if msg.get("type") not in _MOVE_TYPES:
            continue
        move = msg.get("move")
        if not move:
            continue
        depth = _as_int(msg.get("depth")) or 0
        max_depth = max(max_depth, depth)
        prev = deepest.get(move)
        if prev is None or depth >= prev[0]:
            deepest[move] = (depth, msg)

    candidates: list[CandidateLine] = []
    for _depth, msg in deepest.values():
        line = _candidate_from_message(msg, white_to_move=white_to_move)
        if line is not None:
            candidates.append(line)

    candidates.sort(key=CandidateLine.sort_key, reverse=True)
    candidates = candidates[:multipv]

    ranked = [
        CandidateLine(
            move_uci=line.move_uci,
            move_san=line.move_san,
            score_cp=line.score_cp,
            mate=line.mate,
            pv=line.pv,
            rank=index,
        )
        for index, line in enumerate(candidates, start=1)
    ]

    return Analysis(fen=fen, candidates=ranked, depth=max_depth or None)


class ChessApiProvider(AnalysisProvider):
    """WebSocket-backed analysis provider for chess-api.com.

    Args:
        ws_url: WebSocket endpoint (default ``wss://chess-api.com/v1``).
        timeout: Seconds to wait for each message before giving up. The server
            streams progressively, so this bounds the *gap* between messages,
            not total search time.
    """

    def __init__(
        self,
        ws_url: str = "wss://chess-api.com/v1",
        *,
        timeout: float = 15.0,
    ) -> None:
        self._ws_url = ws_url
        self._timeout = timeout

    def analyse(self, fen: str, *, multipv: int, depth: int) -> Analysis:
        variants = max(1, min(multipv, _MAX_VARIANTS))
        depth = max(1, min(depth, _MAX_DEPTH))
        try:
            messages = asyncio.run(self._collect(fen, variants, depth))
        except OSError as exc:  # connection failures, DNS, etc.
            raise AnalysisError(
                f"Could not reach chess-api.com at {self._ws_url}: {exc}"
            ) from exc

        analysis = _build_analysis(fen, messages, multipv=multipv)
        if not analysis.candidates:
            raise AnalysisError(
                f"chess-api.com returned no candidate moves for FEN: {fen}"
            )
        return analysis

    async def _collect(
        self, fen: str, variants: int, depth: int
    ) -> list[dict[str, Any]]:
        """Open the socket, request analysis, and gather streamed messages."""
        request = json.dumps({"fen": fen, "variants": variants, "depth": depth})
        messages: list[dict[str, Any]] = []
        async with websockets.connect(self._ws_url) as ws:
            await ws.send(request)
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=self._timeout)
                except (asyncio.TimeoutError, websockets.ConnectionClosed):
                    break
                try:
                    msg = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(msg, dict):
                    continue
                messages.append(msg)
                if msg.get("type") == "bestmove":
                    break
        return messages
