"""Side-panel rendering: header, tabs (Review / Position / Engine / Chat), help overlay."""

from __future__ import annotations

import chess
import pygame

from ..explain.glossary import definitions
from ..explain.imbalances import plan_ideas
from ..explain.pgn import summary
from ..explain.review import LABEL_SYMBOL, MoveReview, eval_words
from .constants import (
    _ERROR_STATUSES,
    _HELP,
    _PAD,
    _TABS,
)
from .geometry import Rect
from .text import clean_ai, wrap


class PanelMixin:
    """Drawing methods for the side panel; mixed into ChessTutorApp."""

    # -- panel --------------------------------------------------------------- #
    def _draw_panel(self, state) -> None:
        p = self.layout.panel_rect
        panel = Rect(p.x, 0, max(p.width, self.screen.get_width() - p.x), self.screen.get_height())
        self._panel = panel
        pygame.draw.rect(self.screen, self.theme.panel_bg, (panel.x, panel.y, panel.width, panel.height))
        x = panel.x + _PAD
        right = panel.x + panel.width - _PAD
        y = 14

        # Header line 1: status (left) + clocks (right).
        clocks = self.controller.clock_texts()
        clock_w = 0
        if clocks is not None:
            you, opp = clocks
            cs = self._bold_font.render(f"You {you}   {self.controller.opponent_name} {opp}", True,
                                        self.theme.panel_text)
            self.screen.blit(cs, (right - cs.get_width(), y + 3))
            clock_w = cs.get_width() + 12
        status_colour = self.theme.status_thinking if state.thinking else self.theme.panel_text
        for line in wrap(state.status, self._heading_font, panel.width - 2 * _PAD - clock_w)[:2]:
            surf = self._heading_font.render(line, True, status_colour)
            self.screen.blit(surf, (x, y))
            y += surf.get_height() + 2
        # Header line 2: eval in words + where we are in the game.
        bits = []
        eval_cp, eval_mate = self._view_eval(state)
        white_cp = eval_cp
        if eval_mate is not None:
            white_cp = (10_000 - abs(eval_mate)) * (1 if eval_mate > 0 else -1)
        if white_cp is not None:
            bits.append(eval_words(white_cp).capitalize())
        n = len(self.controller.board.move_stack)
        if not self.controller.at_latest or self.controller.analysis_mode:
            bits.append(f"move {self.controller.view_len}/{n}  (Left / Right)")
        if bits:
            y = self._fixed_text("   |   ".join(bits), self._small_font, self.theme.panel_muted, x, y + 2)
        y += 6

        # Tabs.
        self._tab_rects = []
        tx = x
        for i, name in enumerate(_TABS):
            active = i == self.tab
            surf = self._bold_font.render(name, True, self.theme.panel_text if active else self.theme.panel_muted)
            rect = pygame.Rect(tx, y, surf.get_width() + 22, surf.get_height() + 12)
            pygame.draw.rect(self.screen, self.theme.tab_active if active else self.theme.tab_bg, rect,
                             border_radius=6)
            self.screen.blit(surf, (tx + 11, y + 6))
            self._tab_rects.append(rect)
            tx = rect.right + 6
        y += self._tab_rects[0].height + 12

        # Scrollable content.
        chat_h = 46 if self.tab == 3 else 0
        footer_h = 28 + chat_h
        clip = pygame.Rect(panel.x, y, panel.width, panel.height - y - footer_h)
        self.screen.set_clip(clip)
        self._cy = y
        if self.tab == 0:
            self._draw_review_tab(state)
        elif self.tab == 1:
            self._draw_position_tab()
        elif self.tab == 2:
            self._draw_engine_tab(state)
        else:
            self._draw_chat_tab(state)
        self._content_h = self._cy - y
        self.screen.set_clip(None)
        max_scroll = max(0, self._content_h - clip.height)
        self.scroll = min(self.scroll, max_scroll)
        if max_scroll:
            frac = self.scroll / max_scroll
            bar_h = max(30, clip.height * clip.height // max(1, self._content_h))
            by = clip.y + int((clip.height - bar_h) * frac)
            pygame.draw.rect(self.screen, self.theme.tab_bg, (panel.x + panel.width - 6, by, 4, bar_h))

        # Chat input (Chat tab only).
        self._chat_box = None
        if self.tab == 3:
            box = pygame.Rect(x, panel.height - footer_h + 4, panel.width - 2 * _PAD, 36)
            self._chat_box = box
            typing = self.chat_input is not None
            pygame.draw.rect(self.screen, self.theme.tab_bg, box, border_radius=6)
            pygame.draw.rect(self.screen, self.theme.panel_heading if typing else self.theme.eval_bar_border,
                             box, 2, border_radius=6)
            if typing:
                shown = self.chat_input + ("|" if (pygame.time.get_ticks() // 500) % 2 else " ")
                colour = self.theme.panel_text
            else:
                shown, colour = "Ask about this position... (C or click)", self.theme.panel_muted
            surf = self._panel_font.render(shown, True, colour)
            offset = max(0, surf.get_width() - (box.width - 16))
            self.screen.set_clip(box.inflate(-8, -4))
            self.screen.blit(surf, (box.x + 8 - offset, box.y + 10))
            self.screen.set_clip(None)

        # Footer: Import / Export buttons on the right, a notice or key hint on the left.
        self._buttons = []
        bx = panel.x + panel.width - _PAD
        for label, action in (("Export PGN", "export"), ("Import PGN", "import")):
            surf = self._small_font.render(label, True, self.theme.panel_text)
            rect = pygame.Rect(0, panel.height - 27, surf.get_width() + 16, surf.get_height() + 8)
            rect.right = bx
            pygame.draw.rect(self.screen, self.theme.tab_bg, rect, border_radius=5)
            self.screen.blit(surf, (rect.x + 8, rect.y + 4))
            self._buttons.append((rect, action))
            bx = rect.x - 6
        if self._flash and pygame.time.get_ticks() > self._flash_until:
            self._flash = ""
        if self.chat_input is not None:
            hint = "Enter: send    Esc: cancel"
        else:
            hint = self._flash or "?  keys     D  details     H  hint"
        surf = self._small_font.render(hint, True, self.theme.panel_muted)
        self.screen.set_clip(pygame.Rect(x, panel.height - 28, max(0, bx - x - 6), 28))
        self.screen.blit(surf, (x, panel.height - 24))
        self.screen.set_clip(None)

        if self.show_help:
            self._draw_help(panel)

    def _draw_help(self, panel: Rect) -> None:
        overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
        overlay.fill((20, 19, 17, 235))
        self.screen.blit(overlay, (panel.x, 0))
        x, y = panel.x + _PAD + 4, 24
        y = self._fixed_text("Keys", self._heading_font, self.theme.panel_heading, x, y) + 8
        key_w = max(self._bold_font.size(k)[0] for k, _ in _HELP) + 18
        for key, text in _HELP:
            self.screen.blit(self._bold_font.render(key, True, self.theme.panel_text), (x, y))
            self.screen.blit(self._panel_font.render(text, True, self.theme.panel_muted), (x + key_w, y))
            y += 28
        self._fixed_text("Press any key or click to close.", self._small_font, self.theme.panel_muted, x, y + 12)

    def _fixed_text(self, text, font, colour, x: int, y: int) -> int:
        surf = font.render(text, True, colour)
        self.screen.blit(surf, (x, y))
        return y + surf.get_height() + 3

    # Scrolled content helpers (draw at the virtual cursor minus scroll).
    def _w(self, text: str, font=None, colour=None, *, indent: int = 0, gap: int = 3) -> None:
        font = font or self._small_font
        colour = colour or self.theme.panel_text
        panel = self._panel
        x = panel.x + _PAD + indent
        max_w = panel.width - 2 * _PAD - indent - 6
        for line in wrap(text, font, max_w):
            surf = font.render(line, True, colour)
            self.screen.blit(surf, (x, self._cy - self.scroll))
            self._cy += surf.get_height() + 2
        self._cy += gap

    def _bullet(self, text: str, colour=None, *, indent: int = 14) -> None:
        body, col = text, colour
        if text.startswith("+ "):
            body, col = "+ " + text[2:].replace("Now: ", ""), self.theme.good_text
        elif text.startswith("- "):
            body, col = "- " + text[2:].replace("Now: ", ""), self.theme.bad_text
        elif not text.endswith(":"):
            body = "\u00b7 " + text
        self._w(body, self._small_font, col or self.theme.panel_text, indent=indent)

    def _section(self, text: str) -> None:
        self._cy += 10
        self._w(text.upper(), self._small_font, self.theme.panel_muted, gap=4)

    def _divider(self) -> None:
        self._cy += 6
        y = self._cy - self.scroll
        pygame.draw.line(self.screen, self.theme.tab_bg, (self._panel.x + _PAD, y),
                         (self._panel.x + self._panel.width - _PAD, y), 1)
        self._cy += 8

    def _label_colour(self, label: str):
        if label in ("Best", "Excellent", "Checkmate"):
            return self.theme.good_text
        if label == "Inaccuracy":
            return self.theme.warn_text
        if label == "Mistake":
            return (235, 140, 60)
        if label == "Blunder":
            return self.theme.bad_text
        return self.theme.panel_text

    # -- Review tab ---------------------------------------------------------- #
    def _draw_review_card(self, review: MoveReview) -> list[str]:
        """One move, key lines only (D for everything). Returns the terms used."""
        top = self._cy
        colour = self._label_colour(review.label)
        who = self.controller.side_name(review.color)
        symbol = LABEL_SYMBOL.get(review.label, "")
        self._w(f"{review.number}{review.san}{symbol}", self._heading_font, self.theme.panel_text, indent=8, gap=0)
        verdict = f"{review.label} - " if review.label else ""
        self._w(f"{who}  |  {verdict}{review.eval_text}", self._panel_font, colour, indent=8, gap=6)

        points = [p for p in review.points if not p.endswith(":")]
        key: list[tuple[str, tuple[int, int, int]]] = []
        if review.problem:
            key.append((review.problem, self.theme.bad_text))
        if review.better:
            key.append((review.better, self.theme.good_text))
        shown = points if self.show_details else (points[:1] if key else points[:2])
        for text, col in key:
            self._w(text, self._small_font, col, indent=8)
        for p in shown:
            self._bullet(p)
        hidden = len(points) - len(shown)
        if hidden > 0:
            self._w(f"D: {hidden} more", self._small_font, self.theme.panel_muted, indent=8)
        # Coloured accent bar down the left edge of the card.
        h = self._cy - top - 4
        pygame.draw.rect(self.screen, colour, (self._panel.x + 6, top - self.scroll, 4, max(4, h)),
                         border_radius=2)
        self._cy += 4
        return list(review.terms)

    def _draw_review_tab(self, state) -> None:
        c = self.controller
        terms: list[str] = []

        # Notices that matter right now: game over, errors, a "what if?" answer.
        notice = (
            state.headline.startswith("What if")
            or state.status.startswith("Game over")
            or state.status in _ERROR_STATUSES
            or "rejected" in state.status
        ) and c.at_latest
        if notice and (state.headline or state.narrative):
            if state.headline:
                self._w(state.headline, self._bold_font, self.theme.panel_heading, gap=2)
            lines = [ln for ln in state.narrative.split("\n") if ln.strip()]
            for ln in lines if self.show_details else lines[:4]:
                self._w(ln, self._small_font, self.theme.panel_text)
            self._divider()

        if c.analysis_mode:
            self._draw_game_summary()

        v = c.view_len
        review = c.review_for(v - 1) if v else None
        if v and review is None:
            self._w("Analysing the last move...", self._small_font, self.theme.status_thinking)
        if review is not None:
            terms += self._draw_review_card(review)
        prev = c.review_for(v - 2) if v >= 2 else None
        if prev is not None:
            sym = LABEL_SYMBOL.get(prev.label, "")
            self._w(f"Before: {prev.number}{prev.san}{sym}  {prev.label}  ({c.side_name(prev.color)})",
                    self._small_font, self.theme.panel_muted, indent=8)

        coaching = self._current_coaching(state)
        if coaching is not None and c.is_human_turn:
            self._section("Your turn")
            for warning in coaching.warnings[:2]:
                self._w(warning, self._small_font, self.theme.warn_text, indent=8)
            plans = coaching.plans if self.show_details else coaching.plans[:1]
            for plan in plans:
                self._w(f"Plan: {plan}", self._small_font, self.theme.panel_text, indent=8)
            if self.show_hint:
                self._w(coaching.best_text, self._small_font, self.theme.good_text, indent=8)
            else:
                self._w("H: show the engine's move", self._small_font, self.theme.panel_muted, indent=8)
            terms += list(coaching.terms)
        elif not v and not c.analysis_mode and c.at_latest:
            self._w("Make a move - every move (yours and your opponent's) gets reviewed here.",
                    self._small_font, self.theme.panel_muted)
        self._draw_glossary(terms)

    def _draw_game_summary(self) -> None:
        reviews = self.controller.reviews_snapshot()
        total = len(self.controller.board.move_stack)
        counts = summary(reviews)
        done = "" if len(reviews) >= total else f"  ({len(reviews)}/{total} reviewed)"
        self._section(f"Game summary{done}")
        for color in (chess.WHITE, chess.BLACK):
            ct = counts[color]
            self._w(
                f"{self.controller.side_name(color)}:  {ct['Inaccuracy']} ?!   {ct['Mistake']} ?   "
                f"{ct['Blunder']} ??",
                self._small_font, self.theme.panel_text, indent=8, gap=1,
            )
        if self.show_details:
            worst = sorted(
                (r for r in reviews.values() if r.label in ("Mistake", "Blunder")),
                key=lambda r: -(r.win_drop or 0),
            )[:4]
            for r in worst:
                self._w(f"Turning point: {r.title} ({self.controller.side_name(r.color)})",
                        self._small_font, self._label_colour(r.label), indent=8, gap=1)
        self._divider()

    # -- Position tab -------------------------------------------------------- #
    def _draw_position_tab(self) -> None:
        board = self.controller.view_board
        facts = self._facts()
        me = self.controller.human_color if not self.controller.analysis_mode else board.turn
        self._section("Imbalances")
        if not facts:
            self._w("No clear imbalances: the position is balanced and symmetrical.",
                    self._small_font, self.theme.panel_muted, indent=8)
        shown = facts if self.show_details else facts[:5]
        for f in shown:
            colour = (
                self.theme.good_text if f.good_for == me
                else self.theme.bad_text if f.good_for is not None else self.theme.panel_text
            )
            self._w(f.text, self._small_font, colour, indent=8)
        if len(facts) > len(shown):
            self._w(f"D: {len(facts) - len(shown)} more", self._small_font, self.theme.panel_muted, indent=8)
        name = "you" if not self.controller.analysis_mode else self.controller.side_name(me)
        ideas = plan_ideas(board, facts, me)
        if ideas:
            self._section(f"Plan ideas for {name}")
            for text, _sq in ideas if self.show_details else ideas[:3]:
                self._w(text, self._small_font, self.theme.panel_text, indent=8)
        if self.show_details:
            opp = plan_ideas(board, facts, not me)
            if opp:
                self._section(f"Plan ideas for {self.controller.side_name(not me)}")
                for text, _sq in opp:
                    self._w(text, self._small_font, self.theme.panel_text, indent=8)
        self._w("Green = good for you, red = good for the opponent.", self._small_font,
                self.theme.panel_muted, indent=8)
        self._draw_glossary([t for f in facts for t in f.terms])

    # -- Engine tab ---------------------------------------------------------- #
    def _draw_engine_tab(self, state) -> None:
        self._section("Engine lines")
        rows = self._view_rows(state)
        if not rows:
            self._w("No analysis yet.", self._small_font, self.theme.panel_muted, indent=8)
        for row in rows[: (6 if self.show_details else 3)]:
            colour = self.theme.panel_heading if row.is_best else self.theme.panel_text
            loss = "" if row.loss_cp == 0 else f"   (-{row.loss_cp / 100:.2f})"
            self._w(f"{row.move}   {row.score}{loss}", self._bold_font, colour, indent=8, gap=0)
            if row.pv_san or row.pv:
                self._w(row.pv_san or row.pv, self._small_font, self.theme.panel_muted, indent=20)
        self._section("Material")
        white_cap, black_cap = self._captured_pieces()
        self._w(f"White took: {''.join(white_cap) or '-'}", self._glyph_font, indent=8, gap=0)
        self._w(f"Black took: {''.join(black_cap) or '-'}", self._glyph_font, indent=8)
        self._section("Moves")
        for text in self._san_move_rows(limit=200):
            self._w(text, self._mono_font, self.theme.panel_text, indent=8, gap=0)

    # -- Chat tab ------------------------------------------------------------ #
    def _draw_chat_tab(self, state) -> None:
        if self.controller.chat_client is None:
            self._w("The chat needs an LLM: set OPENAI_API_KEY (+ OPENAI_BASE_URL, OPENAI_MODEL) "
                    "in .env.", self._small_font, self.theme.panel_muted)
            return
        same = state.chat_fen == self.controller.view_board.fen()
        if not same or not state.chat:
            self._w("Ask anything about the position on the board.", self._panel_font, self.theme.panel_text)
            self._w("The coach only uses the engine lines and the computed facts, and says so "
                    "when they don't cover your question. The squares it refers to light up.",
                    self._small_font, self.theme.panel_muted)
            for ex in ("What is the plan here?", "Why is my last move a mistake?",
                       "Which piece should I improve?"):
                self._w(f'"{ex}"', self._small_font, self.theme.panel_muted, indent=8, gap=1)
            return
        # Newest exchange first, so the latest answer is always at the top.
        pairs: list[tuple[str, str | None]] = []
        for role, text in state.chat:
            if role == "user":
                pairs.append((text, None))
            elif pairs:
                pairs[-1] = (pairs[-1][0], text)
        for i, (question, answer) in enumerate(reversed(pairs[-5:])):
            if i:
                self._divider()
            self._w(question, self._bold_font, self.theme.panel_muted, gap=6)
            if answer is None:
                self._w("Thinking...", self._small_font, self.theme.status_thinking)
            else:
                for para in clean_ai(answer).split("\n"):
                    if para.strip():
                        self._w(para, self._small_font, self.theme.panel_text, indent=4)

    def _draw_glossary(self, terms: list[str]) -> None:
        if not self.show_glossary:
            return
        defs = definitions(terms)
        if not defs:
            return
        self._section("Glossary")
        for term, text in defs[:8]:
            self._w(f"{term.capitalize()}: {text}", self._small_font, self.theme.panel_muted, indent=8)

    def _san_move_rows(self, *, limit: int) -> list[str]:
        board = self.controller.board
        replay = board.root()
        sans: list[str] = []
        for move in board.move_stack:
            sans.append(replay.san(move))
            replay.push(move)
        rows: list[str] = []
        for i in range(0, len(sans), 2):
            black = sans[i + 1] if i + 1 < len(sans) else ""
            rows.append(f"{i // 2 + 1:>2}. {sans[i]:<8}{black}")
        return rows[-limit:]
