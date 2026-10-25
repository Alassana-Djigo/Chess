"""Client and mapping for the public Lichess API (https://lichess.org/api).

Lichess asks clients to make one request at a time and, after an HTTP 429, to wait a minute
before retrying. The client does both. The mapping functions are pure: they turn Lichess JSON
into small dataclasses and know nothing about the database.
"""

import json
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import quote

import requests

from core.choices import Outcome, TimeCategory
from player.fide import split_titles

BASE_URL = "https://lichess.org"
USER_AGENT = "Chess-stats/0.1 (+https://github.com/Alassana-Djigo/Chess)"
RATE_LIMIT_WAIT = 60  # seconds, as Lichess asks after a 429
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,29}$")
ECO_RE = re.compile(r"^[A-E][0-9]{2}$")

# Lichess speeds and rating pools that map onto our categories. Ultra-bullet and
# correspondence are different rating pools and are left out on purpose.
CATEGORIES = {
    "bullet": TimeCategory.BULLET,
    "blitz": TimeCategory.BLITZ,
    "rapid": TimeCategory.RAPID,
    "classical": TimeCategory.CLASSICAL,
}

_UNFINISHED = {"created", "started"}
_NOT_A_GAME = {"aborted", "noStart", "unknownFinish"}


class LichessError(Exception):
    """Any problem talking to Lichess."""


class LichessNotFound(LichessError):
    """The user or resource does not exist."""


class LichessRateLimited(LichessError):
    """Lichess kept answering 429 after the client waited."""


class LichessClient:
    def __init__(
        self,
        token: str = "",
        session=None,
        sleep: Callable[[float], None] = time.sleep,
        notify: Callable[[str], None] | None = None,
        max_retries: int = 2,
    ):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.sleep = sleep
        self.notify = notify
        self.max_retries = max_retries

    def _get(self, path, params=None, accept="application/json", stream=False):
        url = f"{BASE_URL}{path}"
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    url, params=params, stream=stream, headers={"Accept": accept}, timeout=(10, 60)
                )
            except requests.RequestException as error:
                raise LichessError(f"Could not reach Lichess: {error}") from error

            if response.status_code == 429:
                response.close()
                if attempt == self.max_retries:
                    raise LichessRateLimited(
                        "Lichess is rate limiting this client. Try again in a few minutes."
                    )
                if self.notify:
                    self.notify(f"Lichess asked us to slow down; waiting {RATE_LIMIT_WAIT}s...")
                self.sleep(RATE_LIMIT_WAIT)
                continue
            if response.status_code == 404:
                response.close()
                raise LichessNotFound(path)
            try:
                response.raise_for_status()
            except requests.HTTPError as error:
                response.close()
                raise LichessError(f"Lichess answered {response.status_code} for {path}") from error
            return response

    def _json(self, path, params=None):
        with self._get(path, params) as response:
            try:
                return response.json()
            except ValueError as error:
                raise LichessError(f"Lichess sent an unreadable answer for {path}") from error

    def get_user(self, username: str) -> dict:
        """Public profile, including the FIDE ID when the user has made it public."""
        return self._json(f"/api/user/{quote(username, safe='')}", {"fideId": "true"})

    def get_rating_history(self, username: str) -> list:
        """Without a token Lichess may answer with a cached copy, or an empty list."""
        return self._json(f"/api/user/{quote(username, safe='')}/rating-history")

    def iter_games(self, username: str, max_games: int) -> Iterator[dict]:
        """The user's most recent rated standard games, newest first."""
        path = f"/api/games/user/{quote(username, safe='')}"
        params = {
            "max": max_games,
            "rated": "true",
            "perfType": ",".join(CATEGORIES),
            "opening": "true",
            "moves": "true",
            "pgnInJson": "true",
        }
        with self._get(path, params, accept="application/x-ndjson", stream=True) as response:
            try:
                for line in response.iter_lines():
                    if line:
                        yield json.loads(line)
            except (requests.RequestException, ValueError) as error:
                raise LichessError(f"The game stream was interrupted: {error}") from error


@dataclass(frozen=True)
class LichessProfile:
    id: str
    username: str
    title: str
    real_name: str
    fide_id: int | None
    closed: bool
    ratings: dict[TimeCategory, int]  # current, non-provisional ratings


@dataclass(frozen=True)
class LichessSide:
    username: str
    user_id: str
    title: str
    rating: int | None


@dataclass(frozen=True)
class LichessGame:
    id: str
    white: LichessSide
    black: LichessSide
    outcome: Outcome
    time_category: TimeCategory
    time_base: int | None
    time_increment: int | None
    started_at: datetime
    eco: str
    opening: str
    pgn: str


def parse_profile(data: dict) -> LichessProfile:
    ratings = {}
    for name, perf in (data.get("perfs") or {}).items():
        category = CATEGORIES.get(name)
        if category and perf.get("games", 0) > 0 and not perf.get("prov") and perf.get("rating"):
            ratings[category] = perf["rating"]
    fide_id = data.get("fideId")
    return LichessProfile(
        id=data["id"],
        username=data.get("username") or data["id"],
        title=split_titles(data.get("title") or "", "")[0],
        real_name=((data.get("profile") or {}).get("realName") or "").strip(),
        fide_id=int(fide_id) if fide_id else None,
        closed=bool(data.get("disabled") or data.get("tosViolation")),
        ratings=ratings,
    )


def parse_rating_history(data: list) -> dict[tuple[TimeCategory, date], int]:
    """Map [(category, day)] to the rating on that day. Lichess months start at 0."""
    result = {}
    for entry in data or []:
        category = CATEGORIES.get(entry.get("name"))
        if category is None:
            continue
        for year, month, day, rating in entry.get("points", []):
            try:
                result[(category, date(year, month + 1, day))] = rating
            except ValueError:
                continue
    return result


def _parse_side(side: dict) -> LichessSide | None:
    user = side.get("user")
    if not user:  # Stockfish games and anonymous players have no user
        return None
    return LichessSide(
        username=user["name"],
        user_id=user["id"],
        title=split_titles(user.get("title") or "", "")[0],
        rating=side.get("rating"),
    )


def parse_game(data: dict) -> LichessGame | None:
    """Turn one exported game into a LichessGame, or None if it is not one we can use."""
    category = CATEGORIES.get(data.get("speed"))
    if category is None or data.get("variant") != "standard":
        return None

    status = data.get("status")
    if status in _NOT_A_GAME:
        return None
    winner = data.get("winner")
    if winner == "white":
        outcome = Outcome.WHITE_WINS
    elif winner == "black":
        outcome = Outcome.BLACK_WINS
    elif status in _UNFINISHED:
        outcome = Outcome.ONGOING
    else:
        outcome = Outcome.DRAW  # no winner on a finished game: draw, stalemate, flag vs bare king

    players = data.get("players") or {}
    white, black = _parse_side(players.get("white", {})), _parse_side(players.get("black", {}))
    if white is None or black is None or white.user_id == black.user_id:
        return None

    clock = data.get("clock") or {}
    opening = data.get("opening") or {}
    eco = opening.get("eco", "")
    return LichessGame(
        id=data["id"],
        white=white,
        black=black,
        outcome=outcome,
        time_category=category,
        time_base=clock.get("initial"),
        time_increment=clock.get("increment"),
        started_at=datetime.fromtimestamp(data["createdAt"] / 1000, tz=UTC),
        eco=eco if ECO_RE.match(eco) else "",
        opening=(opening.get("name") or "")[:120],
        pgn=data.get("pgn") or "",
    )
