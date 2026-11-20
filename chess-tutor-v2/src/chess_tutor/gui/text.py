"""Text helpers for the Pygame UI (word-wrap, cleaning AI answers, eval labels)."""

from __future__ import annotations

import re

import pygame

_CITATION = re.compile(r"\s*\[(?:[EF]\d+(?:\s*,\s*)?)+\]")


def wrap(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Greedy word-wrap ``text`` to ``max_width`` pixels for ``font``."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split(" "):
            trial = f"{current} {word}".strip()
            if font.size(trial)[0] <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        lines.append(current)
    return lines


def clean_ai(text: str) -> str:
    """Strip markdown emphasis and fact-ID citations from an AI answer for display.

    The citations still drive the square highlights; they just aren't shown as text.
    """
    text = _CITATION.sub("", text)
    text = text.replace("**", "").replace("__", "")
    lines = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith(("* ", "- ")):
            line = "\u00b7 " + stripped[2:]
        lines.append(line.replace("*", ""))
    return "\n".join(lines)


def eval_label(eval_cp: int | None, eval_mate: int | None) -> str:
    """Compact White-perspective score, e.g. ``+1.3`` or ``M3``."""
    if eval_mate is not None:
        return f"M{abs(eval_mate)}"
    if eval_cp is None:
        return ""
    return f"{eval_cp / 100:+.1f}"
