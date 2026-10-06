"""Typer CLI: play a full game against the hybrid tutor and learn from it.

The tutor is the opponent: on its turn the engine analyses the position, the LLM
"brain" recommends and explains a move, and the hybrid core enforces the engine's
final say (vetoing blunders). On your turn you can ask for a hint, see the
candidate-move comparison, or ask "why not <move>?" before committing.

Rendering helpers at the top are pure functions so they can be unit tested without
a terminal or any network access; the interactive loop lives in :func:`play`.
"""

from __future__ import annotations

import chess
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config import Settings, load_settings
from ..engine.chess_api import ChessApiProvider
from ..engine.hybrid import HybridEngine, MoveDecision
from ..engine.llm import LLMError, side_to_move_name
from ..engine.provider import AnalysisError, AnalysisProvider
from ..engine.teaching import (
    ComparisonRow,
    comparison_rows,
    why_not_move,
    why_this_move,
)

app = typer.Typer(
    add_completion=False,
    help="A hybrid chess tutor: an AI brain proposes moves, the engine has the final say.",
)
console = Console()

# Unicode glyphs for a readable terminal board.
_PIECE_GLYPHS = {
    "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
    "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
}


# --------------------------------------------------------------------------- #
# Pure rendering helpers (unit-testable)
# --------------------------------------------------------------------------- #
def render_board(board: chess.Board, *, perspective: chess.Color = chess.WHITE) -> str:
    """Return a plain-text board drawn from ``perspective``'s point of view."""
    ranks = range(7, -1, -1) if perspective == chess.WHITE else range(8)
    files = range(8) if perspective == chess.WHITE else range(7, -1, -1)
    lines: list[str] = []
    for rank in ranks:
        cells: list[str] = []
        for file in files:
            piece = board.piece_at(chess.square(file, rank))
            cells.append(_PIECE_GLYPHS.get(piece.symbol(), ".") if piece else ".")
        lines.append(f"{rank + 1}  " + " ".join(cells))
    file_labels = "abcdefgh" if perspective == chess.WHITE else "hgfedcba"
    lines.append("   " + " ".join(file_labels))
    return "\n".join(lines)


def build_comparison_table(rows: list[ComparisonRow]) -> Table:
    """Render comparison rows as a Rich table (candidate-move comparison)."""
    table = Table(title="Candidate moves (engine-vetted, best first)")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Move")
    table.add_column("Eval", justify="right")
    table.add_column("Loss", justify="right")
    table.add_column("Line", overflow="fold")
    table.add_column("Coach's note", overflow="fold")
    for row in rows:
        marker = ""
        if row.is_best:
            marker = " ★"
        chosen = " ◀ played" if row.is_chosen else ""
        loss = "-" if row.loss_cp == 0 else f"-{row.loss_cp}"
        style = "bold green" if row.is_chosen else None
        table.add_row(
            str(row.rank),
            f"{row.move}{marker}{chosen}",
            row.score,
            loss,
            row.pv or "-",
            row.comment or "-",
            style=style,
        )
    return table


def format_decision_tag(decision: MoveDecision) -> str:
    """Short, human-readable tag describing who decided the move."""
    label = {
        "llm": "coach",
        "engine-veto": "engine veto",
        "engine-fallback": "engine fallback",
        "engine-only": "engine only",
    }.get(decision.source, decision.source)
    return f"[{label}]"


# --------------------------------------------------------------------------- #
# Interactive helpers
# --------------------------------------------------------------------------- #
def _resolve_user_move(board: chess.Board, text: str) -> chess.Move | None:
    """Parse a user's move (SAN or UCI) into a legal move, or ``None``."""
    text = text.strip()
    if not text:
        return None
    for parser in (board.parse_san, board.parse_uci):
        try:
            move = parser(text)
        except ValueError:
            continue
        if move in board.legal_moves:
            return move
    return None


def _show_board(board: chess.Board, perspective: chess.Color) -> None:
    console.print(Panel(render_board(board, perspective=perspective), expand=False))


def _print_help() -> None:
    console.print(
        "[bold]Commands[/bold]:\n"
        "  <move>        play a move (SAN like 'Nf3' or UCI like 'g1f3')\n"
        "  hint          show the engine candidates + coach's recommendation\n"
        "  why <move>    explain why an alternative move is weaker\n"
        "  board         redraw the board\n"
        "  resign        resign the game\n"
        "  quit          exit\n"
        "  help          show this help"
    )


def _make_engine(settings: Settings, provider: AnalysisProvider) -> HybridEngine:
    engine = HybridEngine.from_settings(settings, provider)
    if not engine.has_llm:
        console.print(
            "[yellow]No OPENAI_API_KEY configured — running engine-only "
            "(moves without the coaching narrative).[/yellow]"
        )
    return engine


def _tutor_moves(board: chess.Board, engine: HybridEngine) -> None:
    """The tutor analyses, selects (engine-authoritative), explains, and plays."""
    console.print("[dim]Tutor is thinking…[/dim]")
    try:
        decision = engine.select_move(board.fen())
    except (AnalysisError, LLMError) as exc:
        console.print(f"[red]Tutor could not move: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    move = chess.Move.from_uci(decision.move_uci)
    san = board.san(move) if move in board.legal_moves else decision.move_uci
    board.push(move)

    console.print(
        f"[bold cyan]Tutor plays {san}[/bold cyan] {format_decision_tag(decision)}"
    )
    console.print(
        build_comparison_table(
            comparison_rows(
                decision.analysis,
                proposal=decision.proposal,
                chosen_uci=decision.move_uci,
            )
        )
    )
    console.print(Panel(why_this_move(decision), title="Why this move", expand=False))


def _handle_player_turn(board: chess.Board, engine: HybridEngine) -> bool:
    """Process one player turn. Returns ``True`` if a move was made."""
    raw = console.input("[bold green]Your move[/bold green] (or command): ").strip()
    if not raw:
        return False
    cmd = raw.lower()

    if cmd in {"quit", "exit"}:
        raise typer.Exit()
    if cmd == "resign":
        console.print("[yellow]You resigned. Good game![/yellow]")
        raise typer.Exit()
    if cmd == "help":
        _print_help()
        return False
    if cmd == "board":
        _show_board(board, board.turn)
        return False
    if cmd == "hint":
        _show_hint(board, engine)
        return False
    if cmd.startswith("why"):
        _answer_why_not(board, engine, raw[3:].strip())
        return False

    move = _resolve_user_move(board, raw)
    if move is None:
        console.print(
            f"[red]'{raw}' is not a legal move (or recognized command). "
            "Type 'help'.[/red]"
        )
        return False
    board.push(move)
    return True


def _show_hint(board: chess.Board, engine: HybridEngine) -> None:
    try:
        decision = engine.select_move(board.fen())
    except (AnalysisError, LLMError) as exc:
        console.print(f"[red]Could not get a hint: {exc}[/red]")
        return
    console.print(
        build_comparison_table(
            comparison_rows(
                decision.analysis,
                proposal=decision.proposal,
                chosen_uci=decision.move_uci,
            )
        )
    )
    console.print(
        Panel(why_this_move(decision), title="Coach's recommendation", expand=False)
    )


def _answer_why_not(board: chess.Board, engine: HybridEngine, move: str) -> None:
    if not move:
        console.print("[yellow]Usage: why <move>  (e.g. 'why e4' or 'why e2e4')[/yellow]")
        return
    try:
        analysis = engine.analyse(board.fen())
    except AnalysisError as exc:
        console.print(f"[red]Could not analyse the position: {exc}[/red]")
        return
    proposal = engine.propose(board.fen(), analysis)
    console.print(
        Panel(
            why_not_move(analysis, move, proposal=proposal),
            title=f"Why not {move}?",
            expand=False,
        )
    )


def _announce_result(board: chess.Board) -> None:
    result = board.result(claim_draw=True)
    if board.is_checkmate():
        winner = "White" if board.turn == chess.BLACK else "Black"
        console.print(f"[bold]Checkmate — {winner} wins![/bold] ({result})")
    elif board.is_stalemate():
        console.print(f"[bold]Stalemate — draw.[/bold] ({result})")
    elif board.is_insufficient_material():
        console.print(f"[bold]Draw — insufficient material.[/bold] ({result})")
    else:
        console.print(f"[bold]Game over.[/bold] ({result})")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
@app.command()
def play(
    color: str = typer.Option(
        "white", "--color", "-c", help="Play as 'white', 'black', or 'random'."
    ),
    depth: int | None = typer.Option(
        None, "--depth", "-d", help="Engine search depth (overrides CHESS_API_DEPTH)."
    ),
    fen: str | None = typer.Option(
        None, "--fen", help="Start from a custom position (FEN)."
    ),
) -> None:
    """Play a full game against the tutor, with coaching after every move."""
    settings = load_settings()
    if depth is not None:
        settings = _with_depth(settings, depth)

    player_color = _choose_color(color)
    board = chess.Board(fen) if fen else chess.Board()

    provider = ChessApiProvider(settings.chess_api_ws_url)
    engine = _make_engine(settings, provider)

    side = "White" if player_color == chess.WHITE else "Black"
    console.print(
        Panel(
            f"You are [bold]{side}[/bold]. "
            f"Engine depth {settings.chess_api_depth}, top {settings.multipv} lines, "
            f"blunder guard {settings.blunder_threshold_cp} cp.\n"
            "Type 'help' for commands.",
            title="Chess Tutor",
            expand=False,
        )
    )

    try:
        _game_loop(board, engine, player_color)
    finally:
        engine.close()


def _game_loop(
    board: chess.Board, engine: HybridEngine, player_color: chess.Color
) -> None:
    while not board.is_game_over(claim_draw=True):
        _show_board(board, player_color)
        console.print(
            f"[dim]{side_to_move_name(board.fen())} to move "
            f"(move {board.fullmove_number}).[/dim]"
        )
        if board.turn == player_color:
            moved = _handle_player_turn(board, engine)
            if not moved:
                continue
        else:
            _tutor_moves(board, engine)
    _show_board(board, player_color)
    _announce_result(board)


# --------------------------------------------------------------------------- #
# Small helpers kept out of the loop for testability
# --------------------------------------------------------------------------- #
def _choose_color(color: str) -> chess.Color:
    value = color.strip().lower()
    if value == "black":
        return chess.BLACK
    if value == "random":
        import secrets

        return chess.WHITE if secrets.randbelow(2) == 0 else chess.BLACK
    return chess.WHITE


def _with_depth(settings: Settings, depth: int) -> Settings:
    from dataclasses import replace

    return replace(settings, chess_api_depth=max(1, depth))


def main() -> None:  # pragma: no cover - thin entrypoint
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
