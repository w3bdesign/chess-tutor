"""Layout and help-text constants shared by the GUI modules."""

from __future__ import annotations

_FPS = 60
_TUTOR_MOVE_DELAY_MS = 350  # small pause so the player sees their move land
_TABS = ("Review", "Position", "Engine", "Chat")
_PAD = 16
_MIN_PANEL = 380
_MIN_SQUARE = 40
_ERROR_STATUSES = ("Engine error.", "Lichess problem.", "Board out of sync with Lichess.")

_HELP = (
    ("Click", "select a piece, click a square to move"),
    ("Right-click a target", "what if I played that?"),
    ("Left / Right, Home / End", "step through the moves"),
    ("1 2 3 4 / Tab", "Review / Position / Engine / Chat"),
    ("D", "more / less detail"),
    ("H", "show the engine's move (your turn)"),
    ("C", "ask the coach (AI) about this position"),
    ("G", "glossary of chess terms"),
    ("I / E", "import / export PGN"),
    ("F", "flip the board"),
    ("N", "new game (resigns a Lichess game)"),
    ("Esc", "close / clear selection"),
)
