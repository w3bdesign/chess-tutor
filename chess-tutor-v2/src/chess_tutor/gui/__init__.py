"""Pygame desktop front-end for the hybrid chess tutor.

This package is a **thin consumer** of the existing engine core. It owns only
presentation and input concerns:

* :mod:`chess_tutor.gui.geometry` -- pure board/layout coordinate math (no
  pygame, no network) so it can be unit tested in isolation.
* :mod:`chess_tutor.gui.theme` -- colours and sizing constants.
* :mod:`chess_tutor.gui.pieces` -- Unicode-glyph piece rendering (cached).
* :mod:`chess_tutor.gui.app` -- the window, event loop and the bridge to the
  :class:`~chess_tutor.engine.hybrid.HybridEngine`.

All chess rules, analysis, LLM coaching and the engine's final-say logic are
reused from :mod:`chess_tutor.engine`; nothing about the game is reimplemented
here (DRY).
"""

from __future__ import annotations
