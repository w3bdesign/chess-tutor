"""The AnalysisProvider interface.

This is the seam that keeps the POC flexible: today a WebSocket-backed
``ChessApiProvider`` calls the hosted chess-api.com engine; later a local
Stockfish UCI backend can implement the same interface and be swapped in with no
changes to the hybrid core, teaching layer, or CLI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Analysis


class AnalysisError(RuntimeError):
    """Raised when an analysis provider cannot produce any analysis."""


class AnalysisProvider(ABC):
    """Abstract chess-engine analysis backend.

    Implementations must return engine analysis for a given FEN, including up to
    ``multipv`` candidate lines sorted best-first. Implementations should degrade
    gracefully and return however many lines are available rather than raising
    when fewer than ``multipv`` are produced.
    """

    @abstractmethod
    def analyse(self, fen: str, *, multipv: int, depth: int) -> Analysis:
        """Analyse ``fen`` and return up to ``multipv`` candidate lines.

        Args:
            fen: Position to analyse, in FEN notation.
            multipv: Desired number of candidate lines (top-N).
            depth: Desired search depth.

        Returns:
            An :class:`~chess_tutor.engine.models.Analysis` with candidates
            sorted best-first (score from the side-to-move perspective).

        Raises:
            AnalysisError: If analysis could not be obtained at all.
        """

    def close(self) -> None:
        """Release any resources (network client, subprocess). Default: no-op."""

    def __enter__(self) -> "AnalysisProvider":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
