# Chess Tutor v2

A desktop chess tutor for club players (~1600) that **explains every move** -
yours and your opponent's - in plain English, with arrows and highlighted squares
on the board, in the spirit of Jeremy Silman's _How to Reassess Your Chess_.

Explanations are **computed, not generated** (the DecodeChess approach):

- **Stockfish** (via chess-api.com) judges move quality.
- **python-chess** computes the board facts (tactics, pawn structure, outposts,
  open files, king safety...).
- **Fixed templates** turn those facts into sentences.

No LLM is involved in the explanations, so they can't hallucinate. An LLM is used
**only on demand** when you chat about a position, and even then it may only use
the computed facts and must cite them.

You can play a human-like, beatable opponent: **Lichess's Maia bots** (maia1 /
maia5 / maia9) through the Lichess Board API, or the local engine.

> This is a proof-of-concept. See [Deferred / next steps](#deferred--next-steps).

---

## Quick start

From the project folder (first time: do [Setup](#setup) and fill in `.env`):

```bash
# Windows (cmd or PowerShell), no activation needed:
.venv\Scripts\python.exe -m chess_tutor.gui.app

# macOS / Linux:
.venv/bin/python -m chess_tutor.gui.app
```

A window opens. With `LICHESS_TOKEN` set it challenges the configured Maia bot
(status shows "Connecting to Lichess (maia5)..."); you play White. Without a token
you play the local engine.

---

## What you get

| Feature | Details |
| --- | --- |
| **Move review (both sides)** | Quality label (Best / Excellent / Good / Inaccuracy / Mistake / Blunder) from the drop in win chance; what the move does (captures, checks, forks, pins, development, attacks); Silman imbalance changes (green = good for the mover, red = bad); for weak moves the punishing engine line with the material it loses, and what was better. |
| **Your turn** | Warnings about your loose pieces, Silman plan ideas derived from the imbalances, and the engine's move hidden until you press **H**. |
| **Position tab** | All imbalances by category (material, minor pieces, pawn structure, space, files, outposts, development, king safety) and plan ideas for both sides. |
| **Engine tab** | Top candidate lines with evals and SAN continuations, captured material, full move list. |
| **"What if?"** | Right-click a legal target square to get a full review of that hypothetical move. |
| **Glossary** | Off by default; press **G** to show definitions of every term used (outpost, backward pawn, bishop pair, ...). |
| **PGN import / export** | **I** imports a PGN (file picker, or a PGN on the clipboard) and reviews every move of both players, with a game summary and the biggest turning points. **E** saves an annotated PGN (`?!` / `?` / `??` + review comments) that Lichess / ChessBase can read. |
| **Browse moves** | **Left / Right** (and **Home / End**) step through the game - in your own games too - showing each move's review, arrows and eval. |
| **Board visuals** | Arrows (green = better move, red = opponent's punishing reply / threats to you, orange = what a move attacks) and blue-outlined squares for the facts being described. |
| **Coach chat (AI)** | Press **C** and ask anything about the current position. The LLM gets the engine lines and the numbered facts, must cite them (e.g. `[F4]`), says when the facts don't cover a question, and the cited squares light up on the board. |
| **Lichess Maia opponent** | Casual games against maia1 (~1100), maia5 (~1500) or maia9 (~1900) from your normal Lichess account, with live clocks. |

---

## How it works

```
                      ┌───────────────────────────┐
  position (FEN) ───▶ │ Stockfish via chess-api   │  top-N lines + evals
                      └─────────────┬─────────────┘  (cached per FEN)
                                    │
                    ┌───────────────┴────────────────┐
                    ▼                                ▼
     ┌──────────────────────────┐     ┌──────────────────────────────┐
     │ explain/review.py        │     │ explain/imbalances.py        │
     │ label, tactics, line     │     │ Silman facts + plan ideas    │
     │ consequences, better     │     │ (pure python-chess rules)    │
     └────────────┬─────────────┘     └──────────────┬───────────────┘
                  └───────────────┬──────────────────┘
                                  ▼
                 ┌────────────────────────────────────┐
                 │ GUI panel + arrows / highlights    │
                 └────────────────┬───────────────────┘
                                  │ only when you press C
                                  ▼
                 ┌────────────────────────────────────┐
                 │ explain/chat.py: LLM, fact IDs in, │
                 │ citations out (OpenAI-compatible)  │
                 └────────────────────────────────────┘
```

- **Move quality** uses Lichess's win-chance model on the Stockfish score before
  and after the move (inaccuracy ≥ 10 %, mistake ≥ 20 %, blunder ≥ 30 % lost).
  The after-move search is preferred because it looks one ply deeper.
- **Consequences** are measured by replaying Stockfish's own line move by move and
  counting material at the first quiet point, so nothing is claimed mid-exchange.
- **Imbalance changes** are compared after the immediate recaptures, so e.g.
  `Bxc6 dxc6` is described as "Black gets the bishop pair; Black gets doubled
  c-pawns".

---

## Requirements

- **Python 3.11+**
- Network access to `chess-api.com` (free engine analysis)
- Optional: a **Lichess API token** (to play Maia)
- Optional: an **OpenAI-compatible LLM key** (for the chat, and for the local tutor's move choice)

---

## Setup

```bash
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Or with [uv](https://docs.astral.sh/uv/): `uv sync --extra dev` (uses the committed `uv.lock`).

Then copy the example environment file and fill it in:

```bash
# Windows:        copy .env.example .env
# macOS / Linux:  cp .env.example .env
```

`.env` is gitignored - never commit keys.

---

## Environment variables

All settings are read from the environment / `.env` (see the annotated
[`.env.example`](.env.example)).

### Opponent: Lichess Maia

| Variable | Default | Description |
| --- | --- | --- |
| `LICHESS_TOKEN` | _(none)_ | Personal token from <https://lichess.org/account/oauth/token/create> with **only** `board:play` + `challenge:write`. When set, you play a Lichess bot; otherwise the local engine plays. A normal account is enough (no BOT account needed). |
| `LICHESS_BOT` | `maia5` | `maia1` (~1100), `maia5` (~1500), `maia9` (~1900). |
| `LICHESS_CLOCK_MINUTES` | `30` | Real-time clock (Maia declines correspondence). |
| `LICHESS_INCREMENT` | `0` | Increment in seconds. |

Games are casual (unrated). **N** aborts (before move 2) or resigns the current
game and starts a new one; closing the window does the same.

### LLM (chat + local tutor), OpenAI-compatible

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | _(none)_ | API key for your provider. Without it the chat is disabled; everything else works. |
| `OPENAI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | Any OpenAI-compatible endpoint (OpenRouter, Gemini, a gateway, a local proxy...). |
| `OPENAI_MODEL` | `gemini-3.1-pro-preview` | Model name. |
| `OPENAI_AUTH_SCHEME` | `Bearer` | Authorization scheme. Only change it if your gateway expects something else (e.g. `Key`). |

### Engine analysis

| Variable | Default | Description |
| --- | --- | --- |
| `CHESS_API_WS_URL` | `wss://chess-api.com/v1` | WebSocket endpoint (MultiPV lines are only streamed here). |
| `CHESS_API_DEPTH` | `13` | Search depth. Higher = more accurate explanations, slower. |
| `MULTIPV` | `3` | Number of candidate lines. |
| `BLUNDER_THRESHOLD_CP` | `80` | Local tutor only: if the LLM's proposed move is this much worse than the engine's best, the engine's move is played instead. |

---

## Usage

Start the GUI (see also [Quick start](#quick-start)):

```bash
# Without activating the venv
.venv\Scripts\python.exe -m chess_tutor.gui.app      # Windows
.venv/bin/python -m chess_tutor.gui.app              # macOS / Linux

# Or, inside an activated venv (Windows: .venv\Scripts\activate,
# macOS / Linux: source .venv/bin/activate)
chess-tutor-gui
```

| Input | Action |
| --- | --- |
| **Left-click** | Select a piece, then click a highlighted square to move (auto-queens). |
| **Right-click** a legal target | "What if I played that?" - full review of the hypothetical move. |
| **1 / 2 / 3** (or click the tabs, **Tab** cycles) | Moves / Position (Silman) / Engine. |
| **H** | Show / hide the engine's suggested move on your turn. |
| **G** | Show / hide the glossary ("Words used"). Off by default. |
| **Left / Right, Home / End** | Step through the moves of the game. |
| **I** | Import a PGN and review it (file picker; cancel to use a PGN on the clipboard). |
| **E** | Export the game as an annotated PGN. |
| **C** | Chat about the current position (Enter sends, Esc cancels). |
| **Mouse wheel** | Scroll the panel. |
| **F** | Flip the board. |
| **N** | New game (resigns / aborts the current Lichess game). |
| **Esc** | Clear the selection. |

The broadcast-style **evaluation bar** on the left always shows White's
perspective and flips with the board.

### Cost model

- **Engine analysis is free** (chess-api.com) and cached per position, shared by
  move reviews, coaching and "what if?".
- **Explanations use zero LLM calls.**
- **Chat:** one LLM call per message you send.
- **Local tutor (no Lichess token):** one LLM call per tutor move if `OPENAI_API_KEY`
  is set (the LLM proposes, the engine can veto); otherwise it plays the engine's move.

---

## Development

```bash
pytest                     # offline tests (live tests excluded by default)
ruff check .               # lint
```

Opt-in live tests against chess-api.com:

```bash
# Windows (cmd):   set "RUN_LIVE_TESTS=1" && pytest -m live
# macOS / Linux:   RUN_LIVE_TESTS=1 pytest -m live
```

Handy scripts (in `scripts/`):

| Script | What it does |
| --- | --- |
| `review_live.py [uci moves...]` | Reviews every move of a game with the real engine and prints the explanations. |
| `explain_demo.py` | Prints reviews / imbalances / plans for a few fixed positions (no network). |
| `chat_live.py ["question"]` | One live chat call about a sample position (costs one LLM request). |
| `gui_render_check.py` | Renders all three tabs headlessly to PNG with a fake engine. |
| `lichess_smoke.py` | Plays 1.e4 against the configured bot on Lichess, then resigns. |
| `lichess_spike.py` | The original Lichess feasibility check. |

---

## Project layout

```
src/chess_tutor/
├── config.py            # env-driven Settings (frozen dataclass)
├── engine/
│   ├── models.py        # CandidateLine, Analysis (eval normalized to side to move)
│   ├── provider.py      # AnalysisProvider interface (engine seam)
│   ├── chess_api.py     # ChessApiProvider over the chess-api.com WebSocket
│   ├── llm.py           # OpenAI-compatible client (+ local tutor's move proposals)
│   ├── hybrid.py        # HybridEngine: LLM proposes, engine has the final say
│   └── teaching.py      # candidate comparison rows, why-not text
├── explain/             # deterministic explanations (no LLM) + grounded chat
│   ├── imbalances.py    # Silman facts + plan ideas
│   ├── review.py        # per-move review, position coaching
│   ├── glossary.py      # beginner definitions of every term used
│   └── chat.py          # fact sheet with IDs, LLM chat, cited squares
├── lichess/
│   ├── client.py        # minimal Board API client (stdlib urllib, NDJSON streams)
│   └── session.py       # one game vs a bot on a background thread, clocks
└── gui/
    ├── theme.py         # colours / sizes (no pygame)
    ├── geometry.py      # square <-> pixel math (no pygame)
    ├── pieces.py        # Unicode-glyph piece rendering
    ├── controller.py    # game flow, threads, analysis cache, reviews, chat (no pygame)
    └── app.py           # window, tabs, arrows, input (chess-tutor-gui)
```

---

## Deferred / next steps

- **Threat scan** ("what does this move threaten / prevent") via null-move engine
  searches, for deeper DecodeChess-style reasoning.
- **Focus lenses** (tactics, opening principles, endgame technique) beyond the
  Silman view.
- **Local Stockfish (UCI)** as another `AnalysisProvider` (faster, deeper, offline).
- **GUI:** promotion picker (currently auto-queens), PGN export, stepping through
  engine lines on the board, browsing reviews of earlier moves.
- **Lichess:** draw offers / takebacks; choosing your colour.

---

## License

MIT
