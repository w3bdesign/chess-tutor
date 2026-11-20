"""Silman-style imbalances computed deterministically from the board (no engine, no LLM).

Every :class:`Fact` is derived from python-chess board state with simple, fixed
rules, carries the squares it is about (for board highlights) and the glossary
terms it uses. Nothing here is guessed: if a rule doesn't fire, no fact is made.

Facts have stable ``key`` values so two positions can be diffed ("this move
created a passed pawn on c5", "this move gave up the bishop pair").
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}
PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}

# Display order of categories (Silman's list).
CATEGORIES = (
    "material",
    "minor pieces",
    "pawn structure",
    "space",
    "files",
    "squares",
    "development",
    "king safety",
)


def color_name(color: chess.Color) -> str:
    return "White" if color == chess.WHITE else "Black"


def sq(square: chess.Square) -> str:
    return chess.square_name(square)


@dataclass(frozen=True)
class Fact:
    """One verified statement about the position."""

    key: str  # stable identity, used for before/after diffs
    category: str  # one of CATEGORIES
    color: chess.Color | None  # side the fact is about (None = both / neutral)
    text: str  # full sentence for the Position view
    good_for: chess.Color | None  # which side benefits (for plans and diffs)
    squares: tuple[chess.Square, ...] = ()
    terms: tuple[str, ...] = ()
    weight: int = 1  # importance for ordering (higher first)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def material(board: chess.Board, color: chess.Color) -> int:
    return sum(VALUES[p.piece_type] for p in board.piece_map().values() if p.color == color)


def _forward(color: chess.Color) -> int:
    return 1 if color == chess.WHITE else -1


def _rel_rank(square: chess.Square, color: chess.Color) -> int:
    """Rank 0..7 counted from ``color``'s own back rank."""
    r = chess.square_rank(square)
    return r if color == chess.WHITE else 7 - r


def _pawns(board: chess.Board, color: chess.Color) -> list[chess.Square]:
    return list(board.pieces(chess.PAWN, color))


def _files_of(squares: list[chess.Square]) -> dict[int, list[chess.Square]]:
    out: dict[int, list[chess.Square]] = {}
    for s in squares:
        out.setdefault(chess.square_file(s), []).append(s)
    return out


def _is_passed(board: chess.Board, square: chess.Square, color: chess.Color) -> bool:
    f, r = chess.square_file(square), chess.square_rank(square)
    for e in board.pieces(chess.PAWN, not color):
        ef, er = chess.square_file(e), chess.square_rank(e)
        if abs(ef - f) <= 1 and ((er > r) if color == chess.WHITE else (er < r)):
            return False
    return True


def _can_be_attacked_by_pawn(board: chess.Board, square: chess.Square, by: chess.Color) -> bool:
    """Could a pawn of ``by`` ever attack ``square`` (now or after advancing)?"""
    f, r = chess.square_file(square), chess.square_rank(square)
    for p in board.pieces(chess.PAWN, by):
        pf, pr = chess.square_file(p), chess.square_rank(p)
        if abs(pf - f) != 1:
            continue
        # A ``by`` pawn attacks squares one rank ahead of it; it must still be behind.
        if (by == chess.WHITE and pr < r) or (by == chess.BLACK and pr > r):
            return True
    return False


def _defended_by_pawn(board: chess.Board, square: chess.Square, color: chess.Color) -> bool:
    return any(
        board.piece_type_at(a) == chess.PAWN and board.color_at(a) == color
        for a in board.attackers(color, square)
    )


def _list(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


# --------------------------------------------------------------------------- #
# extractors
# --------------------------------------------------------------------------- #
def _material_facts(board: chess.Board) -> list[Fact]:
    facts: list[Fact] = []
    w, b = material(board, chess.WHITE), material(board, chess.BLACK)
    if w != b:
        leader = chess.WHITE if w > b else chess.BLACK
        diff = abs(w - b)
        unit = "pawn" if diff == 1 else "pawns"
        facts.append(
            Fact(
                key="material",
                category="material",
                color=leader,
                good_for=leader,
                text=f"{color_name(leader)} is up material: +{diff} {unit} worth "
                f"(pawn=1, knight/bishop=3, rook=5, queen=9).",
                weight=5,
            )
        )
    # The exchange: rook vs minor piece imbalance.
    for color in chess.COLORS:
        rooks = len(board.pieces(chess.ROOK, color)) - len(board.pieces(chess.ROOK, not color))
        minors = (
            len(board.pieces(chess.KNIGHT, color))
            + len(board.pieces(chess.BISHOP, color))
            - len(board.pieces(chess.KNIGHT, not color))
            - len(board.pieces(chess.BISHOP, not color))
        )
        if rooks >= 1 and minors <= -1:
            facts.append(
                Fact(
                    key=f"exchange:{color}",
                    category="material",
                    color=color,
                    good_for=color,
                    text=f"{color_name(color)} has a rook against a minor piece "
                    f"(is 'up the exchange').",
                    terms=("exchange",),
                    weight=4,
                )
            )
    return facts


def _minor_piece_facts(board: chess.Board) -> list[Fact]:
    facts: list[Fact] = []
    for color in chess.COLORS:
        name = color_name(color)
        bishops = list(board.pieces(chess.BISHOP, color))
        enemy_bishops = list(board.pieces(chess.BISHOP, not color))
        light = [b for b in bishops if chess.BB_SQUARES[b] & chess.BB_LIGHT_SQUARES]
        dark = [b for b in bishops if chess.BB_SQUARES[b] & chess.BB_DARK_SQUARES]
        e_light = [b for b in enemy_bishops if chess.BB_SQUARES[b] & chess.BB_LIGHT_SQUARES]
        e_dark = [b for b in enemy_bishops if chess.BB_SQUARES[b] & chess.BB_DARK_SQUARES]
        if light and dark and not (e_light and e_dark):
            facts.append(
                Fact(
                    key=f"bishop_pair:{color}",
                    category="minor pieces",
                    color=color,
                    good_for=color,
                    text=f"{name} has the bishop pair; it gets stronger as the position opens.",
                    squares=tuple(bishops),
                    terms=("bishop pair",),
                    weight=3,
                )
            )
        # Bad bishop: most own pawns fixed on the bishop's square colour.
        pawns = _pawns(board, color)
        for bsq in bishops:
            on_light = bool(chess.BB_SQUARES[bsq] & chess.BB_LIGHT_SQUARES)
            mask = chess.BB_LIGHT_SQUARES if on_light else chess.BB_DARK_SQUARES
            same = [p for p in pawns if chess.BB_SQUARES[p] & mask]
            # "Blocked" pawns can't easily move off the colour.
            blocked = [p for p in same if board.piece_at(p + 8 * _forward(color)) is not None]
            if len(same) >= 4 and len(same) * 3 >= len(pawns) * 2 and blocked:
                shade = "light" if on_light else "dark"
                facts.append(
                    Fact(
                        key=f"bad_bishop:{color}:{shade}",
                        category="minor pieces",
                        color=color,
                        good_for=not color,
                        text=f"{name}'s {shade}-squared bishop on {sq(bsq)} is a bad bishop: "
                        f"{len(same)} of {len(pawns)} own pawns stand on {shade} squares.",
                        squares=(bsq, *same),
                        terms=("bad bishop",),
                        weight=2,
                    )
                )
        # Knight vs bishop balance.
        knights_diff = len(board.pieces(chess.KNIGHT, color)) - len(
            board.pieces(chess.KNIGHT, not color)
        )
        bishops_diff = len(bishops) - len(enemy_bishops)
        if color == chess.WHITE and knights_diff * bishops_diff < 0:
            more_b = chess.WHITE if bishops_diff > 0 else chess.BLACK
            facts.append(
                Fact(
                    key="bishop_vs_knight",
                    category="minor pieces",
                    color=None,
                    good_for=None,
                    text=f"Bishop vs knight: {color_name(more_b)} has the extra bishop, "
                    f"{color_name(not more_b)} the extra knight. Bishops want open "
                    f"positions; knights want closed ones and outposts.",
                    weight=2,
                )
            )
    return facts


def _pawn_facts(board: chess.Board) -> list[Fact]:
    facts: list[Fact] = []
    for color in chess.COLORS:
        name = color_name(color)
        pawns = _pawns(board, color)
        by_file = _files_of(pawns)
        files = sorted(by_file)
        # Passed pawns.
        for p in pawns:
            if _is_passed(board, p, color):
                rr = _rel_rank(p, color)
                facts.append(
                    Fact(
                        key=f"passed:{color}:{sq(p)}",
                        category="pawn structure",
                        color=color,
                        good_for=color,
                        text=f"{name} has a passed pawn on {sq(p)}"
                        + (" - far advanced, very dangerous." if rr >= 5 else "."),
                        squares=(p,),
                        terms=("passed pawn",),
                        weight=4 if rr >= 5 else 3,
                    )
                )
        # Isolated pawns.
        for f, sqs in by_file.items():
            if (f - 1) not in by_file and (f + 1) not in by_file:
                for p in sqs:
                    facts.append(
                        Fact(
                            key=f"isolated:{color}:{sq(p)}",
                            category="pawn structure",
                            color=color,
                            good_for=not color,
                            text=f"{name}'s pawn on {sq(p)} is isolated.",
                            squares=(p,),
                            terms=("isolated pawn",),
                            weight=2,
                        )
                    )
        # Doubled pawns.
        for f, sqs in by_file.items():
            if len(sqs) >= 2:
                facts.append(
                    Fact(
                        key=f"doubled:{color}:{chess.FILE_NAMES[f]}",
                        category="pawn structure",
                        color=color,
                        good_for=not color,
                        text=f"{name} has doubled pawns on the {chess.FILE_NAMES[f]}-file "
                        f"({_list([sq(s) for s in sorted(sqs)])}).",
                        squares=tuple(sqs),
                        terms=("doubled pawns",),
                        weight=2,
                    )
                )
        # Backward pawns: no friendly pawn beside/behind on adjacent files, and the
        # stop square is attacked by an enemy pawn.
        for p in pawns:
            f, rr = chess.square_file(p), _rel_rank(p, color)
            adj = [s for s in pawns if abs(chess.square_file(s) - f) == 1]
            if not adj or rr >= 6:
                continue
            if any(_rel_rank(s, color) <= rr for s in adj):
                continue
            stop = p + 8 * _forward(color)
            if not 0 <= stop < 64:
                continue
            if any(
                board.piece_type_at(a) == chess.PAWN for a in board.attackers(not color, stop)
            ):
                facts.append(
                    Fact(
                        key=f"backward:{color}:{sq(p)}",
                        category="pawn structure",
                        color=color,
                        good_for=not color,
                        text=f"{name}'s pawn on {sq(p)} is backward: it can't be defended by "
                        f"a pawn and {sq(stop)} in front of it is controlled by an enemy pawn.",
                        squares=(p, stop),
                        terms=("backward pawn",),
                        weight=2,
                    )
                )
        # Pawn islands.
        islands = 0
        prev = -2
        for f in files:
            if f != prev + 1:
                islands += 1
            prev = f
        if islands >= 3:
            facts.append(
                Fact(
                    key=f"islands:{color}",
                    category="pawn structure",
                    color=color,
                    good_for=not color,
                    text=f"{name} has {islands} pawn islands (scattered pawns are harder "
                    f"to defend).",
                    squares=tuple(pawns),
                    terms=("pawn islands",),
                    weight=1,
                )
            )
    return facts


def _space_facts(board: chess.Board) -> list[Fact]:
    """Safe squares controlled in the opponent's half (ranks 5-7 from own side)."""
    counts: dict[chess.Color, int] = {}
    for color in chess.COLORS:
        n = 0
        for s in chess.SQUARES:
            rr = _rel_rank(s, color)
            if not 4 <= rr <= 6:
                continue
            if not board.attackers(color, s):
                continue
            if any(board.piece_type_at(a) == chess.PAWN for a in board.attackers(not color, s)):
                continue
            n += 1
        counts[color] = n
    w, b = counts[chess.WHITE], counts[chess.BLACK]
    if abs(w - b) >= 4:
        leader = chess.WHITE if w > b else chess.BLACK
        return [
            Fact(
                key="space",
                category="space",
                color=leader,
                good_for=leader,
                text=f"{color_name(leader)} has more space ({max(w, b)} vs {min(w, b)} safe "
                f"squares controlled in the enemy half). The cramped side should look "
                f"for trades.",
                terms=("space",),
                weight=2,
            )
        ]
    return []


def _file_facts(board: chess.Board) -> list[Fact]:
    facts: list[Fact] = []
    for f in range(8):
        mask = chess.BB_FILES[f]
        w_p = board.pieces(chess.PAWN, chess.WHITE) & chess.SquareSet(mask)
        b_p = board.pieces(chess.PAWN, chess.BLACK) & chess.SquareSet(mask)
        fname = chess.FILE_NAMES[f]
        heavy = {
            c: [
                s
                for s in chess.SquareSet(mask)
                if board.piece_type_at(s) in (chess.ROOK, chess.QUEEN) and board.color_at(s) == c
            ]
            for c in chess.COLORS
        }
        if not w_p and not b_p:
            owners = [c for c in chess.COLORS if heavy[c]]
            if len(owners) == 1:
                c = owners[0]
                facts.append(
                    Fact(
                        key=f"open_file:{fname}:{c}",
                        category="files",
                        color=c,
                        good_for=c,
                        text=f"The {fname}-file is open and {color_name(c)} controls it "
                        f"(rook/queen on {_list([sq(s) for s in heavy[c]])}).",
                        squares=tuple(heavy[c]),
                        terms=("open file",),
                        weight=3,
                    )
                )
            else:
                facts.append(
                    Fact(
                        key=f"open_file:{fname}",
                        category="files",
                        color=None,
                        good_for=None,
                        text=f"The {fname}-file is open"
                        + (" (contested by both sides)." if owners else " - a rook would love it."),
                        squares=tuple(heavy[chess.WHITE] + heavy[chess.BLACK]),
                        terms=("open file",),
                        weight=2,
                    )
                )
        else:
            for c, own, enemy in ((chess.WHITE, w_p, b_p), (chess.BLACK, b_p, w_p)):
                if not own and enemy and heavy[c]:
                    facts.append(
                        Fact(
                            key=f"semi_open:{fname}:{c}",
                            category="files",
                            color=c,
                            good_for=c,
                            text=f"{color_name(c)}'s rook/queen on the semi-open {fname}-file "
                            f"pressures {color_name(not c)}'s pawn on "
                            f"{_list([sq(s) for s in enemy])}.",
                            squares=tuple(heavy[c]) + tuple(enemy),
                            terms=("semi-open file",),
                            weight=2,
                        )
                    )
    return facts


def _square_facts(board: chess.Board) -> list[Fact]:
    """Outposts: squares in the enemy half (c-f files, ranks 4-6) a knight can use."""
    facts: list[Fact] = []
    for color in chess.COLORS:
        name = color_name(color)
        for s in chess.SQUARES:
            if not 2 <= chess.square_file(s) <= 5 or not 3 <= _rel_rank(s, color) <= 5:
                continue
            if not _defended_by_pawn(board, s, color):
                continue
            if _can_be_attacked_by_pawn(board, s, not color):
                continue
            piece = board.piece_at(s)
            if piece and piece.color == color and piece.piece_type in (chess.KNIGHT, chess.BISHOP):
                facts.append(
                    Fact(
                        key=f"outpost_occupied:{color}:{sq(s)}",
                        category="squares",
                        color=color,
                        good_for=color,
                        text=f"{name}'s {PIECE_NAMES[piece.piece_type]} sits on an outpost on "
                        f"{sq(s)}: protected by a pawn, and no enemy pawn can ever chase it.",
                        squares=(s,),
                        terms=("outpost", "hole"),
                        weight=4,
                    )
                )
            elif piece is None or piece.color != color:
                facts.append(
                    Fact(
                        key=f"outpost:{color}:{sq(s)}",
                        category="squares",
                        color=color,
                        good_for=color,
                        text=f"{sq(s)} is an outpost for {name} (a hole in "
                        f"{color_name(not color)}'s camp): a knight there could never be "
                        f"chased by a pawn.",
                        squares=(s,),
                        terms=("outpost", "hole"),
                        weight=2,
                    )
                )
    return facts


_HOME_MINORS = {
    chess.WHITE: {chess.B1: chess.KNIGHT, chess.G1: chess.KNIGHT, chess.C1: chess.BISHOP, chess.F1: chess.BISHOP},
    chess.BLACK: {chess.B8: chess.KNIGHT, chess.G8: chess.KNIGHT, chess.C8: chess.BISHOP, chess.F8: chess.BISHOP},
}


def _castled(board: chess.Board, color: chess.Color) -> bool:
    king = board.king(color)
    if king is None:
        return False
    home = 0 if color == chess.WHITE else 7
    return chess.square_rank(king) == home and chess.square_file(king) in (0, 1, 2, 6, 7)


def is_endgame(board: chess.Board) -> bool:
    """No queens, or little non-pawn material left (king safety/development matter less)."""
    queens = board.pieces(chess.QUEEN, chess.WHITE) | board.pieces(chess.QUEEN, chess.BLACK)
    non_pawn = sum(
        VALUES[p.piece_type]
        for p in board.piece_map().values()
        if p.piece_type not in (chess.PAWN, chess.KING)
    )
    return not queens or non_pawn <= 26


def _development_facts(board: chess.Board) -> list[Fact]:
    if board.fullmove_number > 20 or is_endgame(board):
        return []
    counts: dict[chess.Color, list[chess.Square]] = {}
    for color in chess.COLORS:
        counts[color] = [
            s
            for s, pt in _HOME_MINORS[color].items()
            if board.piece_type_at(s) == pt and board.color_at(s) == color
        ]
    facts: list[Fact] = []
    w, b = len(counts[chess.WHITE]), len(counts[chess.BLACK])
    if w != b and board.fullmove_number >= 4:
        ahead = chess.WHITE if w < b else chess.BLACK
        behind = not ahead
        facts.append(
            Fact(
                key="development",
                category="development",
                color=ahead,
                good_for=ahead,
                text=f"{color_name(ahead)} is ahead in development: {color_name(behind)} "
                f"still has {len(counts[behind])} minor piece(s) at home "
                f"({_list([sq(s) for s in counts[behind]])}).",
                squares=tuple(counts[behind]),
                terms=("development", "initiative"),
                weight=3,
            )
        )
    for color in chess.COLORS:
        king = board.king(color)
        if king is None or _castled(board, color):
            continue
        can_castle = board.has_castling_rights(color)
        if board.fullmove_number >= 8 or not can_castle:
            open_center = not (
                board.pieces(chess.PAWN, chess.WHITE) | board.pieces(chess.PAWN, chess.BLACK)
            ) & chess.SquareSet(chess.BB_FILE_D | chess.BB_FILE_E)
            facts.append(
                Fact(
                    key=f"uncastled:{color}:{can_castle}",
                    category="development",
                    color=color,
                    good_for=not color,
                    text=f"{color_name(color)}'s king is still in the centre"
                    + (" and can no longer castle" if not can_castle else "")
                    + (" with open central files" if open_center else "")
                    + ".",
                    squares=(king,),
                    terms=("castling", "king safety"),
                    weight=3 if (not can_castle or open_center) else 2,
                )
            )
    return facts


def _king_safety_facts(board: chess.Board) -> list[Fact]:
    facts: list[Fact] = []
    for color in chess.COLORS:
        king = board.king(color)
        if king is None:
            continue
        enemy_heavy = board.pieces(chess.QUEEN, not color) | board.pieces(chess.ROOK, not color)
        if not board.pieces(chess.QUEEN, not color) and len(enemy_heavy) < 2:
            continue  # little attacking material left: king safety is secondary
        kf = chess.square_file(king)
        files = [f for f in (kf - 1, kf, kf + 1) if 0 <= f <= 7]
        shield: list[chess.Square] = []
        for f in files:
            for step in (1, 2):
                r = chess.square_rank(king) + step * _forward(color)
                if 0 <= r <= 7:
                    s = chess.square(f, r)
                    if board.piece_type_at(s) == chess.PAWN and board.color_at(s) == color:
                        shield.append(s)
                        break
        open_near = [
            chess.FILE_NAMES[f]
            for f in files
            if not (board.pieces(chess.PAWN, color) & chess.SquareSet(chess.BB_FILES[f]))
        ]
        zone = chess.SquareSet(chess.BB_KING_ATTACKS[king]) | chess.SquareSet(chess.BB_SQUARES[king])
        attackers = {
            a
            for z in zone
            for a in board.attackers(not color, z)
            if board.piece_type_at(a) != chess.PAWN
        }
        problems: list[str] = []
        if len(shield) <= 1 and _castled(board, color):
            problems.append(f"only {len(shield)} shield pawn(s)")
        if open_near:
            problems.append(f"no own pawn on the {_list(open_near)}-file(s) next to it")
        if len(attackers) >= 3:
            problems.append(f"{len(attackers)} enemy pieces hit the squares around it")
        if len(problems) >= 2 or len(attackers) >= 3:
            facts.append(
                Fact(
                    key=f"king_unsafe:{color}",
                    category="king safety",
                    color=color,
                    good_for=not color,
                    text=f"{color_name(color)}'s king on {sq(king)} is exposed: "
                    f"{'; '.join(problems)}.",
                    squares=(king, *sorted(attackers)),
                    terms=("king safety", "pawn shield"),
                    weight=4,
                )
            )
    return facts


def extract(board: chess.Board) -> list[Fact]:
    """All imbalance facts for ``board``, most important first."""
    facts = (
        _material_facts(board)
        + _minor_piece_facts(board)
        + _pawn_facts(board)
        + _space_facts(board)
        + _file_facts(board)
        + _square_facts(board)
        + _development_facts(board)
        + _king_safety_facts(board)
    )
    order = {c: i for i, c in enumerate(CATEGORIES)}
    return sorted(facts, key=lambda f: (-f.weight, order.get(f.category, 99)))


# --------------------------------------------------------------------------- #
# Silman-style plan ideas (rules over the facts above; nothing invented)
# --------------------------------------------------------------------------- #
def plan_ideas(board: chess.Board, facts: list[Fact], color: chess.Color) -> list[tuple[str, tuple[chess.Square, ...]]]:
    """Plan suggestions for ``color`` derived only from ``facts`` (Silman's guidelines)."""
    ideas: list[tuple[str, tuple[chess.Square, ...]]] = []
    seen: set[str] = set()

    def add(text: str, squares: tuple[chess.Square, ...] = ()) -> None:
        if text not in seen:
            seen.add(text)
            ideas.append((text, squares))

    for f in facts:
        kind = f.key.split(":")[0]
        mine = f.color == color
        if kind == "passed" and mine:
            add(f"Push or support your passed pawn on {sq(f.squares[0])}; trade pieces "
                f"to make it stronger.", f.squares)
        elif kind == "passed" and not mine:
            add(f"Blockade the passed pawn on {sq(f.squares[0])}: put a piece (ideally a "
                f"knight) on the square in front of it.", f.squares)
        elif kind == "outpost" and mine:
            add(f"Bring a knight to the outpost on {sq(f.squares[0])}.", f.squares)
        elif kind == "outpost_occupied" and not mine:
            add(f"The enemy piece on {sq(f.squares[0])} is a monster: consider trading it "
                f"off.", f.squares)
        elif kind == "open_file" and f.good_for is None:
            add(f"Put a rook on the open {f.key.split(':')[1]}-file before your opponent "
                f"does.", f.squares)
        elif kind == "open_file" and mine:
            add(f"Double rooks on the {f.key.split(':')[1]}-file and invade on the 7th rank.",
                f.squares)
        elif kind in ("isolated", "backward") and not mine:
            add(f"Target the weak pawn on {sq(f.squares[0])}: attack it with more pieces "
                f"than can defend it.", f.squares)
        elif kind == "bishop_pair" and mine:
            add("You have the bishop pair: open the position (pawn breaks, exchanges of "
                "pawns).", f.squares)
        elif kind == "bad_bishop" and mine:
            add("Your bad bishop: trade it, or move pawns off its colour.", f.squares[:1])
        elif kind == "space" and mine:
            add("You have more space: keep pieces on, avoid trades, expand further.")
        elif kind == "space" and not mine:
            add("You are cramped: trade pieces to free your position.")
        elif kind == "development" and mine:
            add("You're ahead in development: open the position and create threats before "
                "your opponent catches up.")
        elif kind == "development" and not mine:
            add("Finish developing and castle before starting any action.", f.squares)
        elif kind == "uncastled" and mine:
            add("Get your king to safety (castle) soon.", f.squares)
        elif kind == "uncastled" and not mine:
            add("The enemy king is in the centre: open lines (central pawn breaks) to attack "
                "it.", f.squares)
        elif kind == "king_unsafe" and not mine:
            add("The enemy king is exposed: bring more pieces toward it.", f.squares[:1])
        elif kind == "king_unsafe" and mine:
            add("Your king is exposed: defend it, trade attacking pieces (especially the "
                "queen).", f.squares[:1])
        elif kind == "material" and mine:
            add("You're ahead in material: trade pieces (not pawns) and simplify.")
        elif kind == "material" and not mine:
            add("You're behind in material: avoid trades, look for activity and "
                "complications.")
    return ideas[:5]
