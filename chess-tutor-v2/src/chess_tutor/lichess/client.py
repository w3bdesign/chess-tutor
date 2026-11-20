"""Minimal Lichess Board API client (stdlib ``urllib`` only, no extra dependencies).

Only what the tutor needs to play a Lichess bot from a normal account:

* challenge a bot (casual, real-time clock),
* watch the account event stream for ``gameStart`` / ``challengeDeclined``,
* stream a game's state (NDJSON),
* send moves, abort, resign.

Streams are read on daemon threads into a queue so callers can poll them with a
timeout and never block the UI thread. The token is never logged.
"""

from __future__ import annotations

import contextlib
import json
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://lichess.org"


class LichessError(RuntimeError):
    """A Lichess API call failed (HTTP error, bad response, network failure)."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class LichessRateLimited(LichessError):
    """HTTP 429: Lichess asks us to back off (wait at least a minute)."""


class NdjsonStream:
    """Read a Lichess NDJSON stream on a background thread.

    ``get(timeout)`` returns the next JSON object, or ``None`` on timeout.
    ``ended`` becomes ``True`` once the server closes the stream (or it errors).
    """

    def __init__(self, url: str, token: str, *, read_timeout: float = 60.0) -> None:
        self._url = url
        self._token = token
        self._read_timeout = read_timeout
        self._events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._closed = threading.Event()
        self._ended = threading.Event()
        self.connected = threading.Event()  # set once the HTTP response is open
        self._resp: Any = None
        self.error: Exception | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def ended(self) -> bool:
        return self._ended.is_set() and self._events.empty()

    def _run(self) -> None:
        req = urllib.request.Request(
            self._url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/x-ndjson",
            },
        )
        try:
            # Lichess sends a keep-alive newline every few seconds, so a read
            # timeout only fires when the connection is genuinely dead.
            self._resp = urllib.request.urlopen(req, timeout=self._read_timeout)
            self.connected.set()
            for raw in self._resp:
                if self._closed.is_set():
                    break
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    self._events.put(obj)
        except Exception as exc:  # noqa: BLE001 - surfaced via .error
            if not self._closed.is_set():
                self.error = exc
        finally:
            self._ended.set()
            self.connected.set()  # never leave a waiter hanging

    def get(self, timeout: float) -> dict[str, Any] | None:
        try:
            return self._events.get(timeout=max(0.0, timeout))
        except queue.Empty:
            return None

    def close(self) -> None:
        self._closed.set()
        resp = self._resp
        if resp is not None:
            with contextlib.suppress(Exception):  # best effort
                resp.close()


class LichessClient:
    """Thin wrapper over the Lichess HTTP API for Board API play."""

    def __init__(
        self, token: str, *, base_url: str = DEFAULT_BASE_URL, timeout: float = 20.0
    ) -> None:
        if not token:
            raise LichessError("No Lichess token configured (set LICHESS_TOKEN).")
        self._token = token
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    # -- low level ------------------------------------------------------------ #
    def _request(
        self, method: str, path: str, *, form: dict[str, str] | None = None
    ) -> Any:
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self._token}"}
        data: bytes | None = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif method == "POST":
            data = b""
        req = urllib.request.Request(self._base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            if exc.code == 429:
                raise LichessRateLimited(
                    "Lichess rate limit hit (HTTP 429); wait a minute and try again.",
                    status=429,
                ) from None
            raise LichessError(f"Lichess HTTP {exc.code}: {body}", status=exc.code) from None
        except OSError as exc:
            raise LichessError(f"Could not reach Lichess: {exc}") from exc
        if not raw.strip():
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return raw

    def _stream(self, path: str) -> NdjsonStream:
        return NdjsonStream(self._base + path, self._token)

    # -- API ------------------------------------------------------------------ #
    def account(self) -> dict[str, Any]:
        data = self._request("GET", "/api/account")
        return data if isinstance(data, dict) else {}

    def challenge(
        self, username: str, *, color: str, clock_limit_s: int, increment_s: int
    ) -> str:
        """Create a casual real-time challenge and return its id (== game id)."""
        data = self._request(
            "POST",
            f"/api/challenge/{username}",
            form={
                "rated": "false",
                "color": color,
                "clock.limit": str(clock_limit_s),
                "clock.increment": str(increment_s),
            },
        )
        challenge = data.get("challenge", data) if isinstance(data, dict) else None
        cid = challenge.get("id") if isinstance(challenge, dict) else None
        if not cid:
            raise LichessError(f"Unexpected challenge response: {str(data)[:200]}")
        return str(cid)

    def ongoing_game_ids(self) -> set[str]:
        """Ids of the account's games in progress (fallback if an event is missed)."""
        data = self._request("GET", "/api/account/playing")
        games = data.get("nowPlaying", []) if isinstance(data, dict) else []
        return {str(g.get("gameId") or g.get("fullId", "")[:8]) for g in games if isinstance(g, dict)}

    def cancel_challenge(self, challenge_id: str) -> None:
        self._request("POST", f"/api/challenge/{challenge_id}/cancel")

    def stream_events(self) -> NdjsonStream:
        return self._stream("/api/stream/event")

    def stream_game(self, game_id: str) -> NdjsonStream:
        return self._stream(f"/api/board/game/stream/{game_id}")

    def make_move(self, game_id: str, uci: str) -> None:
        self._request("POST", f"/api/board/game/{game_id}/move/{uci}")

    def abort(self, game_id: str) -> None:
        self._request("POST", f"/api/board/game/{game_id}/abort")

    def resign(self, game_id: str) -> None:
        self._request("POST", f"/api/board/game/{game_id}/resign")
