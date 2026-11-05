"""Client and mapping for the Chess.com published-data API (https://api.chess.com/pub).

The API allows unlimited serial access and blocks parallel requests, so the client makes one
request at a time and, after an HTTP 429, waits before trying again. The mapping functions are
pure: they turn Chess.com JSON into small dataclasses and know nothing about the database.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

import requests

from core.choices import Outcome, TimeCategory
from player.fide import split_titles

BASE_URL = "https://api.chess.com"
DEFAULT_CONTACT = "https://github.com/Alassana-Djigo/Chess"
RATE_LIMIT_WAIT = 30  # seconds
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,50}$")
ECO_HEADER_RE = re.compile(r'\[ECO "([A-E][0-9]{2})"\]')
ECO_URL_HEADER_RE = re.compile(r'\[ECOUrl "([^"]+)"\]')
TIME_CONTROL_RE = re.compile(r"^(\d+)(?:\+(\d+))?$")

# Daily (correspondence style) games are a different rating pool and are left out on purpose.
CATEGORIES = {
    "bullet": TimeCategory.BULLET,
    "blitz": TimeCategory.BLITZ,
    "rapid": TimeCategory.RAPID,
}
DRAW_RESULTS = {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}


class ChesscomError(Exception):
    """Any problem talking to Chess.com."""


class ChesscomNotFound(ChesscomError):
    """The player or resource does not exist (or will never exist)."""


class ChesscomRateLimited(ChesscomError):
    """Chess.com kept answering 429 after the client waited."""


class ChesscomClient:
    def __init__(
        self,
        contact: str = "",
        session=None,
        sleep: Callable[[float], None] = time.sleep,
        notify: Callable[[str], None] | None = None,
        max_retries: int = 2,
    ):
        self.session = session or requests.Session()
        # Chess.com asks for a recognisable user agent with contact information.
        self.session.headers["User-Agent"] = (
            f"Chess-stats/0.1 (contact: {contact or DEFAULT_CONTACT})"
        )
        self.sleep = sleep
        self.notify = notify
        self.max_retries = max_retries

    def _get_json(self, url: str):
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    url, headers={"Accept": "application/json"}, timeout=(10, 60)
                )
            except requests.RequestException as error:
                raise ChesscomError(f"Could not reach Chess.com: {error}") from error

            with response:
                if response.status_code == 429:
                    if attempt == self.max_retries:
                        raise ChesscomRateLimited(
                            "Chess.com is rate limiting this client. Try again in a few minutes."
                        )
                    if self.notify:
                        self.notify(
                            f"Chess.com asked us to slow down; waiting {RATE_LIMIT_WAIT}s..."
                        )
                    self.sleep(RATE_LIMIT_WAIT)
                    continue
                if response.status_code in (404, 410):
                    raise ChesscomNotFound(url)
                try:
                    response.raise_for_status()
                except requests.HTTPError as error:
                    raise ChesscomError(
                        f"Chess.com answered {response.status_code} for {url}"
                    ) from error
                try:
                    return response.json()
                except ValueError as error:
                    raise ChesscomError(f"Chess.com sent an unreadable answer for {url}") from error

    def _player_url(self, username: str, suffix: str = "") -> str:
        return f"{BASE_URL}/pub/player/{quote(username.lower(), safe='')}{suffix}"

    def get_profile(self, username: str) -> dict:
        return self._get_json(self._player_url(username))

    def get_stats(self, username: str) -> dict:
        return self._get_json(self._player_url(username, "/stats"))

    def get_archives(self, username: str) -> list[str]:
        """URLs of the monthly archives, oldest first."""
        return self._get_json(self._player_url(username, "/games/archives")).get("archives", [])

    def get_month(self, url: str) -> list[dict]:
        """The games of one monthly archive, as listed by `get_archives`."""
        if not url.startswith(f"{BASE_URL}/pub/player/"):
            raise ChesscomError(f"Unexpected archive address: {url}")
        return self._get_json(url).get("games", [])


@dataclass(frozen=True)
class ChesscomProfile:
    username: str
    player_id: int | None
    name: str
    title: str
    women_title: str
    avatar: str
    closed: bool


@dataclass(frozen=True)
class ChesscomSide:
    username: str
    rating: int | None


@dataclass(frozen=True)
class ChesscomGame:
    id: str
    white: ChesscomSide
    black: ChesscomSide
    outcome: Outcome
    time_category: TimeCategory
    time_base: int | None
    time_increment: int | None
    ended_at: datetime
    eco: str
    opening: str
    pgn: str
    tournament: str  # the tournament's URL slug, or ""


def parse_profile(data: dict) -> ChesscomProfile:
    title, women_title = split_titles(data.get("title") or "", "")
    return ChesscomProfile(
        username=data["username"],
        player_id=data.get("player_id"),
        name=(data.get("name") or "").strip(),
        title=title,
        women_title=women_title,
        avatar=data.get("avatar") or "",
        closed=str(data.get("status") or "").startswith("closed"),
    )


def parse_stats(data: dict) -> dict[TimeCategory, int]:
    """Current rating per pool: rapid, blitz and bullet. Pools never played are absent."""
    ratings = {}
    for name, category in CATEGORIES.items():
        rating = ((data.get(f"chess_{name}") or {}).get("last") or {}).get("rating")
        if rating:
            ratings[category] = rating
    return ratings


def _slug(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1] if url else ""


def opening_from_url(url: str) -> str:
    """'.../Sicilian-Defense-Najdorf-Variation-6.Be3-e5' -> 'Sicilian Defense Najdorf Variation'."""
    words = []
    for word in _slug(url).split("-"):
        if re.match(r"^\d+\.", word):  # the slug continues with moves: stop there
            break
        words.append(word)
    return " ".join(words)[:120]


def is_titled_tuesday(tournament_slug: str) -> bool:
    return "titled-tuesday" in tournament_slug.lower()


def tournament_name(slug: str) -> str:
    """'titled-tuesday-blitz-october-21-2025-6229391' -> 'Titled Tuesday Blitz October 21 2025'."""
    words = slug.split("-")
    if len(words) > 1 and words[-1].isdigit() and len(words[-1]) >= 5:
        words = words[:-1]
    return " ".join(words).title()[:200]


def _outcome(white_result: str, black_result: str) -> Outcome | None:
    if white_result == "win":
        return Outcome.WHITE_WINS
    if black_result == "win":
        return Outcome.BLACK_WINS
    if white_result in DRAW_RESULTS and black_result in DRAW_RESULTS:
        return Outcome.DRAW
    return None  # abandoned games and anything we do not recognise


def parse_game(data: dict) -> ChesscomGame | None:
    """Turn one archived game into a ChesscomGame, or None if it is not one we can use."""
    category = CATEGORIES.get(data.get("time_class"))
    if category is None or data.get("rules") != "chess" or data.get("rated") is False:
        return None
    white, black = data.get("white") or {}, data.get("black") or {}
    outcome = _outcome(white.get("result", ""), black.get("result", ""))
    if outcome is None or not white.get("username") or not black.get("username"):
        return None
    if white["username"].lower() == black["username"].lower():
        return None

    control = TIME_CONTROL_RE.match(str(data.get("time_control", "")))
    pgn = data.get("pgn") or ""
    eco_header = ECO_HEADER_RE.search(pgn)
    url_header = ECO_URL_HEADER_RE.search(pgn)
    return ChesscomGame(
        id=_slug(data.get("url", "")),
        white=ChesscomSide(white["username"], white.get("rating")),
        black=ChesscomSide(black["username"], black.get("rating")),
        outcome=outcome,
        time_category=category,
        time_base=int(control.group(1)) if control else None,
        time_increment=int(control.group(2) or 0) if control else None,
        ended_at=datetime.fromtimestamp(data["end_time"], tz=UTC),
        eco=eco_header.group(1) if eco_header else "",
        opening=opening_from_url(url_header.group(1) if url_header else data.get("eco", "")),
        pgn=pgn,
        tournament=_slug(data.get("tournament", "")),
    )


def ratings_from_games(username: str, games: list[ChesscomGame]) -> dict:
    """The rating after the player's last game of each day, as {(category, date): rating}."""
    points = {}
    for game in sorted(games, key=lambda g: g.ended_at):
        side = game.white if game.white.username.lower() == username.lower() else game.black
        if side.username.lower() == username.lower() and side.rating:
            points[(game.time_category, game.ended_at.date())] = side.rating
    return points
