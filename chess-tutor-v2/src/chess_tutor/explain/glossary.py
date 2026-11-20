"""Beginner-friendly definitions for every chess term the explainer uses.

Explanations tag the terms they use; the GUI shows the matching definitions so a
learner never meets jargon without an explanation next to it.
"""

from __future__ import annotations

GLOSSARY: dict[str, str] = {
    "imbalance": (
        "Any difference between the two sides (material, pawns, pieces, space, king "
        "safety...). Silman: find the imbalances, then make a plan that uses yours."
    ),
    "outpost": (
        "A square in the enemy half, protected by your pawn, that no enemy pawn can "
        "ever attack. A knight there is very strong and hard to remove."
    ),
    "hole": (
        "A square that can no longer be defended by your own pawns; the opponent's "
        "pieces can settle on it."
    ),
    "passed pawn": (
        "A pawn with no enemy pawns in front of it on its own or neighbouring files. "
        "Nothing but pieces can stop it from promoting."
    ),
    "isolated pawn": (
        "A pawn with no friendly pawns on the neighbouring files. Only pieces can "
        "defend it, and the square in front of it is a natural outpost for the enemy."
    ),
    "doubled pawns": (
        "Two pawns of the same colour on one file. They cannot protect each other and "
        "the front one blocks the back one."
    ),
    "backward pawn": (
        "A pawn whose neighbours have advanced past it, so no pawn can defend it, and "
        "whose advance square is controlled by an enemy pawn."
    ),
    "pawn islands": (
        "Groups of pawns separated by empty files. Fewer islands = a healthier, "
        "easier-to-defend structure."
    ),
    "bishop pair": (
        "Having both bishops while the opponent does not. Strong in open positions, "
        "because together they cover squares of both colours."
    ),
    "bad bishop": (
        "A bishop hemmed in by its own pawns standing on its square colour. It has few "
        "squares and mostly defends."
    ),
    "open file": (
        "A file with no pawns on it. Rooks and queens love open files: they can use "
        "them to invade the enemy position."
    ),
    "semi-open file": (
        "A file with only enemy pawns on it (none of yours). Your rook there pressures "
        "the enemy pawn."
    ),
    "space": (
        "How much of the board your pieces and pawns control. More space = more room "
        "to manoeuvre; the cramped side should trade pieces."
    ),
    "development": (
        "Bringing pieces off their starting squares into play. In the opening, the "
        "side that develops faster usually gets the initiative."
    ),
    "initiative": (
        "Being the one making threats, so the opponent has to react instead of "
        "following their own plan."
    ),
    "king safety": (
        "How well the king is sheltered: pawns in front of it, no open lines towards it, "
        "few enemy attackers nearby."
    ),
    "pawn shield": (
        "The pawns directly in front of a castled king. Missing shield pawns create "
        "open lines for the attacker."
    ),
    "castling": (
        "A special move that puts the king in safety and brings a rook toward the "
        "centre in one move."
    ),
    "fork": "One piece attacking two (or more) enemy pieces at the same time.",
    "pin": (
        "A piece that cannot move (or should not) because a more valuable piece, often "
        "the king, is behind it on the same line."
    ),
    "hanging": "A piece that is attacked and not adequately defended - it can be taken for free.",
    "exchange": (
        "'Winning the exchange' = winning a rook for a bishop or knight (about 2 pawns "
        "of value)."
    ),
    "centipawn": (
        "1/100 of a pawn. Engine evaluations are in pawns: +1.00 means White is about "
        "a pawn better."
    ),
    "inaccuracy": "A move that lowers your winning chances a little (lost 10-20% win chance).",
    "mistake": "A move that clearly worsens your position (lost 20-30% win chance).",
    "blunder": "A move that throws away a lot - often material or the game (lost 30%+ win chance).",
}


def definitions(terms: list[str] | tuple[str, ...]) -> list[tuple[str, str]]:
    """``(term, definition)`` pairs for ``terms`` (deduplicated, known terms only)."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for term in terms:
        if term in seen or term not in GLOSSARY:
            continue
        seen.add(term)
        out.append((term, GLOSSARY[term]))
    return out
