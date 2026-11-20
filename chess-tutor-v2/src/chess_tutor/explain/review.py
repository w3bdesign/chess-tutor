"""Explain any move (yours or the opponent's) from engine numbers + board facts.

DecodeChess-style symbolic explanation, no LLM:

* **Verdict** - quality label from the drop in win chance (Stockfish scores before
  and after the move), eval in words.
* **What it does** - exact board facts: captures, checks, castling, development,
  attacks on undefended/higher-value pieces, forks, new pins.
* **Consequence** - material counted along Stockfish's own continuation, replayed
  move by move with python-chess ("loses a knight after ...Bxf7+ Kxf7 Ng5+").
* **Imbalance changes** - Silman facts before vs after ("creates a passed pawn").
* **Better was** - the engine's move with the same kind of facts.

Every statement carries squares/arrows so the GUI can show it on the board.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import chess

from ..engine.models import Analysis, CandidateLine
from .imbalances import PIECE_NAMES, VALUES, Fact, color_name, extract, material, sq

MATE_CP = 10_000

LABEL_SYMBOL = {
    "Best": "!",
    "Excellent": "",
    "Good": "",
    "Inaccuracy": "?!",
    "Mistake": "?",
    "Blunder": "??",
    "Checkmate": "#",
}
LABEL_TERMS = {"Inaccuracy": "inaccuracy", "Mistake": "mistake", "Blunder": "blunder"}


@dataclass(frozen=True)
class Arrow:
    from_sq: chess.Square
    to_sq: chess.Square
    kind: str  # "played" | "best" | "reply" | "attack"


@dataclass(frozen=True)
class MoveReview:
    """A fully explained move. All text is derived from engine + board facts."""

    ply: int  # index into the game's move stack (0 = White's first move)
    color: chess.Color
    move_uci: str
    san: str
    number: str  # "12." or "12..."
    label: str  # Best / Excellent / Good / Inaccuracy / Mistake / Blunder / Checkmate / ""
    eval_text: str  # eval after the move in words (White's perspective)
    points: tuple[str, ...] = ()  # what the move does / changes
    problem: str = ""  # what it allows (for weak moves)
    better: str = ""  # "Better was ..." (for weak moves)
    arrows: tuple[Arrow, ...] = ()
    marks: tuple[chess.Square, ...] = ()
    terms: tuple[str, ...] = ()
    win_drop: float | None = None

    @property
    def title(self) -> str:
        sym = LABEL_SYMBOL.get(self.label, "")
        tail = f"  {self.label}" if self.label else ""
        return f"{self.number} {self.san}{sym}{tail}"


# --------------------------------------------------------------------------- #
# scores
# --------------------------------------------------------------------------- #
def line_cp(line: CandidateLine) -> int | None:
    """Side-to-move centipawns, with mates mapped near +/-MATE_CP."""
    if line.mate is not None:
        if line.mate > 0:
            return MATE_CP - line.mate
        if line.mate < 0:
            return -MATE_CP - line.mate
        return -MATE_CP  # mate 0: the side to move is already mated
    return line.score_cp


def win_percent(cp: int) -> float:
    """Lichess's win-chance model (0..100) for a side-to-move centipawn score."""
    cp = max(-1500, min(1500, cp))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def classify(drop: float) -> str:
    if drop >= 30:
        return "Blunder"
    if drop >= 20:
        return "Mistake"
    if drop >= 10:
        return "Inaccuracy"
    if drop >= 4:
        return "Good"
    return "Excellent"


def eval_words(white_cp: int | None) -> str:
    """Plain-English evaluation from White's perspective."""
    if white_cp is None:
        return "evaluation unknown"
    if abs(white_cp) >= MATE_CP - 500:
        n = MATE_CP - abs(white_cp)
        side = "White" if white_cp > 0 else "Black"
        return f"{side} has a forced mate in {n}" if n > 0 else f"{side} is mating"
    side = "White" if white_cp > 0 else "Black"
    a = abs(white_cp)
    pawns = f"{white_cp / 100:+.1f}"
    if a <= 30:
        return f"the position is equal ({pawns})"
    if a <= 90:
        return f"{side} is slightly better ({pawns})"
    if a <= 200:
        return f"{side} is better ({pawns})"
    if a <= 500:
        return f"{side} is clearly better ({pawns})"
    return f"{side} is winning ({pawns})"


# --------------------------------------------------------------------------- #
# board facts about a single move
# --------------------------------------------------------------------------- #
@dataclass
class _Facts:
    points: list[str] = field(default_factory=list)
    arrows: list[Arrow] = field(default_factory=list)
    marks: list[chess.Square] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)


_HOME_SQUARES = {
    chess.WHITE: {chess.B1, chess.G1, chess.C1, chess.F1},
    chess.BLACK: {chess.B8, chess.G8, chess.C8, chess.F8},
}
_CENTER = {chess.D4, chess.E4, chess.D5, chess.E5}


def _piece_word(piece_type: int) -> str:
    return PIECE_NAMES[piece_type]


def _is_loose(board: chess.Board, square: chess.Square) -> bool:
    """Attacked piece that is undefended, or attacked by something cheaper."""
    piece = board.piece_at(square)
    if piece is None or piece.piece_type == chess.KING:
        return False
    attackers = board.attackers(not piece.color, square)
    if not attackers:
        return False
    if not board.attackers(piece.color, square):
        return True
    cheapest = min(VALUES[board.piece_type_at(a)] or 100 for a in attackers)
    return cheapest < VALUES[piece.piece_type]


def move_facts(board: chess.Board, move: chess.Move) -> _Facts:
    """What ``move`` does on ``board`` (position before the move). Pure board facts."""
    out = _Facts()
    mover = board.turn
    piece = board.piece_at(move.from_square)
    if piece is None:
        return out
    pname = _piece_word(piece.piece_type)
    after = board.copy(stack=False)
    after.push(move)

    if board.is_castling(move):
        side = "kingside" if chess.square_file(move.to_square) > 4 else "queenside"
        out.points.append(f"Castles {side}: the king gets to safety and a rook comes "
                          f"toward the centre.")
        out.terms.append("castling")
    if board.is_capture(move):
        if board.is_en_passant(move):
            out.points.append("Captures a pawn en passant.")
        else:
            victim = board.piece_type_at(move.to_square)
            if victim is not None:
                out.points.append(f"Captures the {_piece_word(victim)} on {sq(move.to_square)}.")
    if move.promotion:
        out.points.append(f"Promotes to a {_piece_word(move.promotion)}!")
    if after.is_checkmate():
        out.points.append("Checkmate!")
        return out
    if board.gives_check(move):
        out.points.append("Gives check.")

    # Development / centre (opening).
    if board.fullmove_number <= 15:
        if piece.piece_type in (chess.KNIGHT, chess.BISHOP) and move.from_square in _HOME_SQUARES[mover]:
            out.points.append(f"Develops the {pname} (brings it off its starting square).")
            out.terms.append("development")
        if piece.piece_type == chess.PAWN and move.to_square in _CENTER:
            out.points.append(f"Occupies the centre with a pawn on {sq(move.to_square)}.")

    # New attacks by the moved piece.
    targets: list[chess.Square] = []
    for t in after.attacks(move.to_square):
        victim = after.piece_at(t)
        if victim is None or victim.color == mover:
            continue
        if victim.piece_type == chess.KING:
            targets.append(t)
            continue
        defended = bool(after.attackers(victim.color, t))
        mover_val = VALUES[after.piece_type_at(move.to_square) or chess.PAWN]
        if not defended or VALUES[victim.piece_type] > mover_val:
            targets.append(t)
    non_king = [t for t in targets if after.piece_type_at(t) != chess.KING]
    if len(targets) >= 2:
        names = [f"{_piece_word(after.piece_type_at(t) or chess.PAWN)} on {sq(t)}" for t in targets]
        out.points.append(f"Forks: the {pname} attacks the " + " and the ".join(names) + ".")
        out.terms.append("fork")
    elif non_king:
        t = non_king[0]
        victim_type = after.piece_type_at(t) or chess.PAWN
        why = "undefended" if not after.attackers(not mover, t) else "more valuable"
        out.points.append(f"Attacks the {why} {_piece_word(victim_type)} on {sq(t)}.")
    for t in targets:
        out.arrows.append(Arrow(move.to_square, t, "attack"))

    # New absolute pins against the opponent.
    for s, p in after.piece_map().items():
        if p.color == mover or p.piece_type == chess.KING:
            continue
        if after.is_pinned(not mover, s) and not board.is_pinned(not mover, s):
            out.points.append(f"Pins the {_piece_word(p.piece_type)} on {sq(s)} to its king "
                              f"(it can't move without exposing the king).")
            out.terms.append("pin")
            out.marks.append(s)
    return out


def _hanging_after(board: chess.Board, move: chess.Move) -> list[chess.Square]:
    """Mover's pieces that are loose after the move but weren't before."""
    mover = board.turn
    after = board.copy(stack=False)
    after.push(move)
    out = []
    for s, p in after.piece_map().items():
        if p.color != mover or p.piece_type == chess.KING:
            continue
        was = board.piece_at(s) == p and _is_loose(board, s)
        if _is_loose(after, s) and not was:
            out.append(s)
    return out


# --------------------------------------------------------------------------- #
# engine lines
# --------------------------------------------------------------------------- #
def _continuation(line: CandidateLine | None, first_uci: str | None = None) -> list[str]:
    """The line's full PV starting with its own move (providers differ on whether the
    PV includes it), minus ``first_uci`` when given (i.e. what follows that move)."""
    if line is None:
        return []
    pv = list(line.pv)
    if not pv or pv[0] != line.move_uci:
        pv = [line.move_uci, *pv]
    if first_uci is not None and pv and pv[0] == first_uci:
        pv = pv[1:]
    return pv


def resolve_line(
    board: chess.Board, pv: list[str], mover: chess.Color, *, max_plies: int = 6
) -> tuple[int, list[str], chess.Board]:
    """Play ``pv`` on a copy of ``board`` until things calm down.

    Returns ``(material change for mover, SAN moves played, final board)``. The
    line stops at the last "quiet" point (the next move is not a capture), so the
    material count is not taken in the middle of an exchange.
    """
    b = board.copy(stack=False)
    start = material(b, mover) - material(b, not mover)
    sans: list[str] = []
    best_end = (0, 0)  # (plies, material) at the last stable point
    for i, uci in enumerate(pv[:max_plies]):
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break
        if move not in b.legal_moves:
            break
        sans.append(b.san(move))
        b.push(move)
        nxt = None
        if i + 1 < len(pv[:max_plies]):
            try:
                nxt = chess.Move.from_uci(pv[i + 1])
            except ValueError:
                nxt = None
        stable = nxt is None or nxt not in b.legal_moves or not b.is_capture(nxt)
        if stable:
            best_end = (i + 1, material(b, mover) - material(b, not mover) - start)
    plies, delta = best_end
    final = board.copy(stack=False)
    for uci in pv[:plies]:
        final.push(chess.Move.from_uci(uci))
    return delta, sans[:plies], final


def _material_words(n: int) -> str:
    n = abs(n)
    if n == 1:
        return "a pawn"
    if n == 2:
        return "two pawns' worth of material"
    if n == 3:
        return "a piece's worth of material (3)"
    return f"material worth {n} pawns"


def _line_text(board: chess.Board, sans: list[str]) -> str:
    """Number SAN moves from ``board``'s side to move, e.g. '12...Bxf7+ 13.Kxf7'."""
    out: list[str] = []
    num = board.fullmove_number
    white = board.turn == chess.WHITE
    for i, s in enumerate(sans):
        if white:
            out.append(f"{num}.{s}")
        elif i == 0:
            out.append(f"{num}...{s}")
        else:
            out.append(s)
        if not white:
            num += 1
        white = not white
    return " ".join(out)


# --------------------------------------------------------------------------- #
# imbalance diff
# --------------------------------------------------------------------------- #
# Material is reported from the engine line (never mid-exchange); empty outposts,
# space counts and island counts change too often to be meaningful per move.
_DIFF_SKIP = ("outpost:", "space", "islands:", "material", "exchange:")


def settle(board: chess.Board, pv: list[str], *, max_plies: int = 3) -> tuple[chess.Board, list[str]]:
    """Play the engine's immediate recaptures (captures only) so diffs aren't mid-exchange."""
    b = board.copy(stack=False)
    sans: list[str] = []
    for uci in pv[:max_plies]:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break
        if move not in b.legal_moves or not b.is_capture(move):
            break
        sans.append(b.san(move))
        b.push(move)
    return b, sans


def imbalance_changes(
    before: list[Fact], after: list[Fact], move: chess.Move, mover: chess.Color, *, limit: int = 3
) -> tuple[list[str], list[chess.Square], list[str]]:
    """Silman imbalance changes caused by a move, from the mover's point of view."""
    bk = {f.key: f for f in before if not f.key.startswith(_DIFF_SKIP)}
    ak = {f.key: f for f in after if not f.key.startswith(_DIFF_SKIP)}
    new = [f for k, f in ak.items() if k not in bk]
    gone = [f for k, f in bk.items() if k not in ak]
    # A pawn that simply advanced keeps its property: don't report gone+new noise.
    moved_new = {f.key.rsplit(":", 1)[0] for f in new if move.to_square in f.squares}
    gone = [
        f for f in gone
        if not (move.from_square in f.squares and f.key.rsplit(":", 1)[0] in moved_new)
    ]
    new = [
        f for f in new
        if not (move.to_square in f.squares
                and any(g.key.rsplit(":", 1)[0] == f.key.rsplit(":", 1)[0]
                        and move.from_square in g.squares for g in bk.values()))
    ]
    items: list[tuple[int, str, Fact]] = []
    for f in new:
        sign = "+" if f.good_for == mover else ("-" if f.good_for is not None else "")
        items.append((f.weight, f"{sign} Now: {f.text}".strip(), f))
    for f in gone:
        sign = "-" if f.good_for == mover else ("+" if f.good_for is not None else "")
        items.append((f.weight, f"{sign} No longer: {f.text}".strip(), f))
    items.sort(key=lambda x: -x[0])
    lines, marks, terms = [], [], []
    for _w, text, f in items[:limit]:
        lines.append(text)
        marks.extend(f.squares[:3])
        terms.extend(f.terms)
    return lines, marks, terms


# --------------------------------------------------------------------------- #
# the review
# --------------------------------------------------------------------------- #
def _number(board: chess.Board) -> str:
    return f"{board.fullmove_number}." if board.turn == chess.WHITE else f"{board.fullmove_number}..."


def review_move(
    board: chess.Board,
    move: chess.Move,
    before: Analysis | None,
    after: Analysis | None,
    *,
    ply: int | None = None,
) -> MoveReview:
    """Explain ``move`` played in ``board`` (the position *before* the move).

    ``before`` is the engine analysis of ``board``; ``after`` the analysis of the
    position after the move (opponent to move). Either may be ``None`` - the
    review then simply contains fewer facts; nothing is invented to fill gaps.
    """
    mover = board.turn
    uci = move.uci()
    san = board.san(move)
    number = _number(board)
    after_board = board.copy(stack=False)
    after_board.push(move)
    ply_index = ply if ply is not None else len(board.move_stack)

    best = before.best if before else None
    played_line = before.find(uci) if before else None

    # Score of the played move (mover's perspective).
    played: int | None
    if after_board.is_checkmate():
        played = MATE_CP
    elif after_board.is_game_over():
        played = 0
    elif after is not None and after.best is not None:
        # The after-move search looks one ply deeper, so it catches traps the
        # pre-move search can miss (e.g. 5.Nxf7?? Qxg2).
        opp = line_cp(after.best)
        played = None if opp is None else -opp
    elif played_line is not None:
        played = line_cp(played_line)
    else:
        played = None
    best_cp = line_cp(best) if best else None

    drop: float | None = None
    label = ""
    if after_board.is_checkmate():
        label = "Checkmate"
    elif played is not None and best_cp is not None:
        drop = max(0.0, win_percent(best_cp) - win_percent(played))
        label = classify(drop)
        if best is not None and best.move_uci == uci and label in ("Excellent", "Good"):
            label = "Best"
    elif best is not None and best.move_uci == uci:
        label = "Best"
        drop = 0.0

    white_cp = None if played is None else (played if mover == chess.WHITE else -played)
    eval_text = eval_words(white_cp)

    facts = move_facts(board, move)
    points = list(facts.points)
    arrows = [Arrow(move.from_square, move.to_square, "played"), *facts.arrows]
    marks = list(facts.marks)
    terms = list(facts.terms)
    if label in LABEL_TERMS:
        terms.append(LABEL_TERMS[label])

    # Consequence along the engine's line after the move.
    reply_pv = (
        _continuation(after.best)
        if after is not None and after.best is not None
        else _continuation(played_line, uci)
    )

    # Imbalance changes (Silman), measured after any immediate recaptures.
    settled, settle_sans = settle(after_board, reply_pv)
    if not settle_sans and board.is_capture(move) and not reply_pv:
        # No engine line: assume nothing about the recapture, but don't report
        # changes that only exist mid-exchange either.
        changes, cmarks, cterms = [], [], []
    else:
        changes, cmarks, cterms = imbalance_changes(extract(board), extract(settled), move, mover)
    if changes and settle_sans:
        changes = [f"After {_line_text(after_board, settle_sans)}:"] + changes
    points.extend(changes)
    marks.extend(cmarks)
    terms.extend(cterms)
    if changes:
        terms.append("imbalance")
    problem = ""
    if reply_pv and not after_board.is_game_over():
        weak = label in ("Inaccuracy", "Mistake", "Blunder")
        # Losses: follow the punishing line further. Gains: only the immediate
        # exchange, so long engine lines aren't sold as "wins a pawn".
        delta, sans, _final = resolve_line(after_board, reply_pv, mover, max_plies=6 if weak else 2)
        capture_gain = 0
        if board.is_capture(move):
            victim = chess.PAWN if board.is_en_passant(move) else board.piece_type_at(move.to_square)
            capture_gain = VALUES[victim or chess.PAWN]
        total = delta + capture_gain
        line = _line_text(after_board, sans)
        reply = chess.Move.from_uci(reply_pv[0]) if reply_pv else None
        if weak:
            opp_mate = after.best.mate if (after and after.best) else None
            if opp_mate is None and played_line is not None and played_line.mate is not None and played_line.mate < 0:
                opp_mate = -played_line.mate
            if opp_mate and opp_mate > 0:
                problem = f"It allows a forced mate in {opp_mate}: {line}"
            elif total < 0:
                problem = f"It loses {_material_words(total)} after {line}"
            elif line:
                problem = f"The opponent's best reply is {line}"
            hanging = _hanging_after(board, move)
            if hanging and total < 0:
                names = [f"{_piece_word(after_board.piece_type_at(s) or chess.PAWN)} on {sq(s)}"
                         for s in hanging[:2]]
                problem += f" (the {' and '.join(names)} is left hanging)"
                terms.append("hanging")
                marks.extend(hanging[:2])
            if problem:
                problem += "."
            if reply is not None:
                arrows.append(Arrow(reply.from_square, reply.to_square, "reply"))
        elif total > 0 and line and (board.is_capture(move) or board.gives_check(move)):
            points.append(f"Wins {_material_words(total)}: {line}.")
        elif board.is_capture(move) and total == 0 and capture_gain:
            points.append("An even trade.")

    # What was better.
    better = ""
    if best is not None and label in ("Inaccuracy", "Mistake", "Blunder") and best.move_uci != uci:
        try:
            bmove = chess.Move.from_uci(best.move_uci)
        except ValueError:
            bmove = None
        if bmove is not None and bmove in board.legal_moves:
            bsan = board.san(bmove)
            bfacts = move_facts(board, bmove)
            b_after = board.copy(stack=False)
            b_after.push(bmove)
            _d, bsans, _ = resolve_line(b_after, _continuation(best, best.move_uci), mover, max_plies=4)
            bwhite = None if best_cp is None else (best_cp if mover == chess.WHITE else -best_cp)
            parts = [f"Better was {number}{bsan} ({eval_words(bwhite)})."]
            parts.extend(bfacts.points[:2])
            if bsans:
                parts.append(f"Line: {_line_text(b_after, bsans)}.")
            better = " ".join(parts)
            arrows.append(Arrow(bmove.from_square, bmove.to_square, "best"))
            terms.extend(bfacts.terms)
    mating = played_line is not None and bool(played_line.mate) and (played_line.mate or 0) > 0
    if (
        best is not None
        and best.mate is not None
        and best.mate > 0
        and label not in ("Best", "Checkmate")
        and not mating
    ):
        points.insert(0, f"Missed a forced mate in {best.mate}.")

    return MoveReview(
        ply=ply_index,
        color=mover,
        move_uci=uci,
        san=san,
        number=number,
        label=label,
        eval_text=eval_text,
        points=tuple(points),
        problem=problem,
        better=better,
        arrows=tuple(arrows),
        marks=tuple(dict.fromkeys(marks)),
        terms=tuple(dict.fromkeys(terms)),
        win_drop=drop,
    )


# --------------------------------------------------------------------------- #
# coaching the side to move (no LLM)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PositionCoaching:
    eval_text: str
    warnings: tuple[str, ...]  # your loose pieces, checks against you
    best_text: str  # engine's move explained
    plans: tuple[str, ...]  # Silman plan ideas for the side to move
    arrows: tuple[Arrow, ...] = ()
    marks: tuple[chess.Square, ...] = ()
    terms: tuple[str, ...] = ()


def coach_position(board: chess.Board, analysis: Analysis | None) -> PositionCoaching:
    """Template coaching for the side to move: dangers, engine move explained, plans."""
    from .imbalances import plan_ideas  # local import keeps module graph simple

    me = board.turn
    best = analysis.best if analysis else None
    cp = line_cp(best) if best else None
    white_cp = None if cp is None else (cp if me == chess.WHITE else -cp)

    warnings: list[str] = []
    marks: list[chess.Square] = []
    arrows: list[Arrow] = []
    terms: list[str] = []
    loose = [s for s, p in board.piece_map().items() if p.color == me and _is_loose(board, s)]
    for s in loose[:3]:
        p = board.piece_type_at(s) or chess.PAWN
        how = "undefended" if not board.attackers(me, s) else "attacked by a cheaper piece"
        warnings.append(f"Your {_piece_word(p)} on {sq(s)} is under attack ({how}).")
        marks.append(s)
        terms.append("hanging")
        for a in list(board.attackers(not me, s))[:1]:
            arrows.append(Arrow(a, s, "reply"))
    if board.is_check():
        warnings.insert(0, "You are in check.")

    best_text = ""
    if best is not None:
        try:
            bmove = chess.Move.from_uci(best.move_uci)
        except ValueError:
            bmove = None
        if bmove is not None and bmove in board.legal_moves:
            bf = move_facts(board, bmove)
            b_after = board.copy(stack=False)
            b_after.push(bmove)
            _d, bsans, _ = resolve_line(b_after, _continuation(best, best.move_uci), me, max_plies=4)
            parts = [f"Engine's move: {_number(board)}{board.san(bmove)}."]
            parts.extend(bf.points[:3])
            if bsans:
                parts.append(f"Expected line: {_line_text(b_after, bsans)}.")
            best_text = " ".join(parts)
            arrows.append(Arrow(bmove.from_square, bmove.to_square, "best"))
            terms.extend(bf.terms)

    facts = extract(board)
    ideas = plan_ideas(board, facts, me)
    plans = tuple(text for text, _sq in ideas)
    for _t, squares in ideas[:3]:
        marks.extend(squares[:2])
    for f in facts:
        terms.extend(f.terms)

    return PositionCoaching(
        eval_text=eval_words(white_cp),
        warnings=tuple(warnings),
        best_text=best_text,
        plans=plans,
        arrows=tuple(arrows),
        marks=tuple(dict.fromkeys(marks)),
        terms=tuple(dict.fromkeys(terms)),
    )


__all__ = [
    "Arrow",
    "MoveReview",
    "PositionCoaching",
    "classify",
    "coach_position",
    "color_name",
    "eval_words",
    "move_facts",
    "resolve_line",
    "review_move",
    "win_percent",
]
