"""Native file dialogs (Tk) for PGN import / export."""

from __future__ import annotations


def _tk_root():
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def ask_pgn_text() -> str | None:
    """File picker for a .pgn; if cancelled, fall back to a PGN on the clipboard."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = _tk_root()
    except Exception:  # noqa: BLE001 - no Tk available
        return None
    try:
        path = filedialog.askopenfilename(
            parent=root, title="Import PGN", filetypes=[("PGN files", "*.pgn"), ("All files", "*.*")]
        )
        if path:
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        try:
            clip = root.clipboard_get()
        except tk.TclError:
            clip = ""
        return clip if "1." in clip else None
    finally:
        root.destroy()


def ask_save_path() -> str | None:
    try:
        from tkinter import filedialog

        root = _tk_root()
    except Exception:  # noqa: BLE001
        return None
    try:
        return filedialog.asksaveasfilename(
            parent=root,
            title="Export annotated PGN",
            defaultextension=".pgn",
            initialfile="chess-tutor-game.pgn",
            filetypes=[("PGN files", "*.pgn")],
        ) or None
    finally:
        root.destroy()
