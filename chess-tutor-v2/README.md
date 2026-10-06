# Chess Tutor v2

A **hybrid chess tutor**: a large language model is the _brain_ that proposes moves
with plain-English reasoning, while a chess engine (Stockfish) has the **final
say** on move quality. Think of it as _Stockfish with an AI coach bolted on_ — the
AI explains and recommends, but the engine vetoes anything that would be a blunder.

The teaching experience is built around **candidate-move comparison**: for each
position the engine surfaces its top few lines, and the coach explains _why this
move_ and _why not that one_, so you learn by weighing real alternatives rather
than memorizing a single "best" answer.

> This is a proof-of-concept (POC). It is intentionally minimal and ships with a
> Python CLI and an optional Pygame desktop GUI (chess.com "Green" board theme),
> both thin front-ends over the same reusable hybrid core. See
> [Deferred / extension points](#deferred--extension-points) for what is planned
> but out of scope for the POC.

---

## How it works

```
                 ┌──────────────────────────────┐
   position ───▶ │  AnalysisProvider (engine)   │  top-N candidate lines
   (FEN)         │  chess-api.com (Stockfish 18) │  with eval + principal
                 └──────────────┬───────────────┘  variation (MultiPV)
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │  LLMClient (the "brain")      │  ONE grounded call →
                 │  OpenAI-compatible SDK        │  recommended move + summary
                 └──────────────┬───────────────┘  + per-candidate why/why-not
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │  Hybrid core (engine = final  │  veto/fallback if the LLM's
                 │  say, blunder guardrail)      │  pick loses > threshold cp
                 └──────────────────────────────┘
```

1. The **engine** (via the `AnalysisProvider` seam) analyses the position and
   returns the top candidate lines (MultiPV), each with an evaluation normalized
   to the side-to-move and a principal variation.
2. The **LLM** receives those engine-vetted candidates and, in a _single_ call,
   returns a recommended move, a short summary, and a "why this / why not"
   comment for **every** candidate.
3. The **hybrid core** enforces that the engine has the final say: if the LLM's
   choice is worse than the engine's best by more than `BLUNDER_THRESHOLD_CP`
   centipawns, the engine's best move overrides it.

The LLM only ever chooses among moves the engine has already vetted, so it can
coach and prioritize but never play an illegal or losing move unchecked.

---

## Requirements

- **Python 3.11+**
- An **OpenAI-compatible** LLM API key (defaults target Gemini's
  OpenAI-compatible endpoint; any OpenAI-compatible provider works)
- Network access to `chess-api.com` for engine analysis (POC backend)

---

## Setup

This project uses [**uv**](https://docs.astral.sh/uv/) for dependency management
and a committed [`uv.lock`](uv.lock) for reproducible installs, with
[**ruff**](https://docs.astral.sh/ruff/) for linting/formatting. The setuptools
build backend is retained.

### With uv (recommended)

If `uv` is on your `PATH`, drop the `python -m` prefix from the commands below.

```bash
# Create the virtual environment and install everything (incl. dev tools)
python -m uv sync --extra dev
```

`uv sync` creates a `.venv/` and installs the exact versions pinned in
`uv.lock`. To add or bump a dependency, edit `pyproject.toml` and run
`python -m uv lock` followed by `python -m uv sync --extra dev`.

### With pip (alternative)

```bash
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
python -m pip install -e ".[dev]"
```

### Configure environment

Copy the example file and fill in your API key:

```bash
# Windows:        copy .env.example .env
# macOS / Linux:  cp .env.example .env
```

---

## Environment variables

All settings are environment-driven (loaded via `python-dotenv` from `.env`).
See [`.env.example`](.env.example) for the annotated source of truth.

### LLM (the "brain", OpenAI-compatible)

| Variable          | Default                                                    | Description                                                      |
| ----------------- | ---------------------------------------------------------- | ---------------------------------------------------------------- |
| `OPENAI_API_KEY`  | _(none)_                                                   | API key for your provider. Required to use the coach.            |
| `OPENAI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | OpenAI-compatible base URL (Gemini, OpenRouter, local proxy, …). |
| `OPENAI_MODEL`    | `gemini-3.1-pro-preview`                                   | Model name — swap any model without changing code.               |

### Chess engine analysis (the "authority")

| Variable               | Default                  | Description                                                                                                   |
| ---------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `CHESS_API_WS_URL`     | `wss://chess-api.com/v1` | WebSocket endpoint. MultiPV candidate lines are streamed here (POST returns only one move).                   |
| `CHESS_API_DEPTH`      | `13`                     | Search depth requested from the engine (higher = stronger + slower).                                          |
| `MULTIPV`              | `3`                      | Number of candidate lines to request — powers the comparison coaching.                                        |
| `BLUNDER_THRESHOLD_CP` | `80`                     | If the LLM's move is worse than the engine's best by more than this many centipawns, the engine overrides it. |

---

## Usage (CLI)

> **Status: forthcoming.** The CLI entry point `chess-tutor`
> (`chess_tutor.cli.main:app`, a Typer app) is declared in
> [`pyproject.toml`](pyproject.toml) but not yet implemented. Once available it
> will let you play a full game, render the board, pick your color and search
> depth, see the candidate-move comparison and "why this move" narrative after
> each move, ask "why not `<move>`?", and resign / start a new game.

Planned invocation:

```bash
# With uv
python -m uv run chess-tutor

# Or, inside an activated venv
chess-tutor
```

---

## Development

### Run tests

Offline tests (fast; network tests are excluded by default via the `live` marker):

```bash
python -m uv run pytest            # or: pytest
```

Opt-in **live** tests that hit the real `chess-api.com` service (require network):

```bash
# Windows (cmd):
set "RUN_LIVE_TESTS=1" && python -m uv run pytest -m live
# macOS / Linux:
RUN_LIVE_TESTS=1 python -m uv run pytest -m live
```

Run the full suite (offline + live):

```bash
python -m uv run pytest -m "live or not live"
```

### Lint & format

```bash
python -m uv run ruff check .
python -m uv run ruff format .
```

---

## Project layout

```
chess-tutor-v2/
├── pyproject.toml          # project metadata, deps, ruff + pytest config
├── uv.lock                 # committed lockfile for reproducible installs
├── .env.example            # annotated environment variables
└── src/chess_tutor/
    ├── config.py           # env-driven Settings (frozen dataclass)
    ├── cli/                # Typer CLI (forthcoming)
    └── engine/
        ├── models.py       # CandidateLine, Analysis (eval normalized to side-to-move)
        ├── provider.py     # AnalysisProvider interface (engine seam)
        ├── chess_api.py    # ChessApiProvider over chess-api.com WebSocket
        └── llm.py          # LLMClient: grounded recommend + why-this/why-not
```

### Key abstractions

- **`AnalysisProvider`** ([`engine/provider.py`](src/chess_tutor/engine/provider.py)) —
  the abstract engine backend. The POC implementation is
  **`ChessApiProvider`** over the chess-api.com WebSocket; a local Stockfish UCI
  backend can be dropped in later behind the same interface.
- **`CandidateLine` / `Analysis`** ([`engine/models.py`](src/chess_tutor/engine/models.py)) —
  immutable engine results, with evaluations normalized to the side to move.
- **`LLMClient`** ([`engine/llm.py`](src/chess_tutor/engine/llm.py)) — a thin
  wrapper over any OpenAI-compatible chat endpoint. One call per move returns a
  `MoveProposal` with the recommended move, a summary, and per-candidate
  comparisons (`comment_for()` powers "why not `<move>`?").

---

## Deferred / extension points

Intentionally out of scope for the POC, but the design leaves clear seams:

- **Local Stockfish (UCI)** — swap chess-api.com for a local engine by adding a
  new `AnalysisProvider` implementation; nothing else changes.
- **Docker** — containerized deployment (engine + CLI/service).
- **FastAPI / HTTP API / MCP** — expose the hybrid core as a web API or an MCP
  server for other tools to consume; the engine and LLM layers are already
  decoupled from the (CLI) presentation layer.

---

## License

MIT
