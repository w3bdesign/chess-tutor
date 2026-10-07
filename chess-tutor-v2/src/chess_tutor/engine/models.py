"""Shared data models for engine analysis.

These dataclasses are provider-agnostic: whether the analysis comes from the
hosted chess-api.com service today or a local Stockfish UCI process later, the
rest of the app (hybrid core, teaching layer, CLI) only depends on these types.

Evaluation convention
---------------------
All ``score_cp`` values are centipawns **from the perspective of the side to
move** (positive = good for the side to move). ``mate`` is the number of moves
to mate from the side-to-move perspective (positive = side to move delivers
mate, negative = side to move gets mated).

Note: chess-api.com reports eval from White's perspective, so providers must
normalize (negate when it is Black to move) before constructing these models.
This keeps the hybrid core and coaching logic simple: "bigger is always better
for the player about to move".
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CandidateLine:
    """A single candidate move and its principal variation.

    Attributes:
        move_uci: The candidate move in UCI form (e.g. ``"e2e4"``).
        move_san: The candidate move in SAN form (e.g. ``"e4"``) when available.
        score_cp: Centipawn evaluation from the side-to-move perspective.
            ``None`` when the line is a forced mate (see ``mate``).
        mate: Moves-to-mate from the side-to-move perspective, or ``None``.
        pv: The principal variation as a list of UCI moves (best play that
            follows), used to ground explanations in concrete lines.
        rank: 1-based rank of this line (1 = engine's best).
    """

    move_uci: str
    move_san: str | None = None
    score_cp: int | None = None
    mate: int | None = None
    pv: list[str] = field(default_factory=list)
    rank: int = 0

    @property
    def is_mate(self) -> bool:
        return self.mate is not None

    def score_text(self) -> str:
        """Human-readable score, e.g. ``"+1.35"`` or ``"#3"``/``"#-2"``."""
        if self.mate is not None:
            return f"#{self.mate}" if self.mate >= 0 else f"#-{abs(self.mate)}"
        if self.score_cp is None:
            return "?"
        return f"{self.score_cp / 100:+.2f}"

    def sort_key(self) -> tuple[int, float]:
        """Best-first ordering key (higher is better for the side to move).

        Mates sort above/below all centipawn scores depending on sign; a faster
        mate for the side to move beats a slower one.
        """
        if self.mate is not None:
            if self.mate >= 0:
                # Delivering mate: fewer moves is better -> very large score.
                return (1, 1_000_000 - self.mate)
            # Getting mated: later is "less bad"; always worse than any cp score.
            return (-1, -1_000_000 - self.mate)
        return (0, float(self.score_cp if self.score_cp is not None else 0))


@dataclass(frozen=True)
class Analysis:
    """Engine analysis of a single position.

    Attributes:
        fen: The analysed position (FEN).
        candidates: Candidate lines sorted best-first (``candidates[0]`` is the
            engine's top choice). May contain fewer than the requested count if
            the provider returned fewer lines (graceful degradation).
        depth: Search depth reached, when reported by the provider.
    """

    fen: str
    candidates: list[CandidateLine]
    depth: int | None = None

    @property
    def best(self) -> CandidateLine | None:
        return self.candidates[0] if self.candidates else None

    def find(self, move_uci: str) -> CandidateLine | None:
        """Return the candidate matching ``move_uci``, if the engine listed it."""
        for line in self.candidates:
            if line.move_uci == move_uci:
                return line
        return None
