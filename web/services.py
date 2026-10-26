"""Queries behind the pages: ratings, results summary, recent games and player search."""

from dataclasses import dataclass, field
from datetime import date

from django.db.models import Max, OuterRef, Q, Subquery

from core.choices import Outcome, Source, TimeCategory
from history_rating.models import HistoryRating
from matches.models import Match
from player.models import Player

SOURCE_LABELS = {
    Source.FIDE: "FIDE",
    Source.LICHESS: "Lichess",
    Source.CHESSCOM: "Chess.com",
    Source.MANUAL: "Manual",
}
CATEGORY_LABELS = {
    TimeCategory.CLASSICAL: "Clássico",
    TimeCategory.RAPID: "Rápido",
    TimeCategory.BLITZ: "Blitz",
    TimeCategory.BULLET: "Bullet",
}
SOURCE_ORDER = list(SOURCE_LABELS)
CATEGORY_ORDER = list(CATEGORY_LABELS)


@dataclass(frozen=True)
class RatingRow:
    """A player's most recent rating in one rating pool."""

    source: str
    category: str
    rating: int
    date: date

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS[self.source]

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS[self.category]


def latest_ratings(player: Player) -> list[RatingRow]:
    """The newest rating per (source, category), FIDE first and classical first."""
    newest = {}
    for row in HistoryRating.objects.filter(player=player).order_by("rating_date"):
        newest[(row.source, row.time_category)] = row
    ordered = sorted(
        newest,
        key=lambda key: (SOURCE_ORDER.index(key[0]), CATEGORY_ORDER.index(key[1])),
    )
    return [
        RatingRow(
            source,
            category,
            newest[(source, category)].rating,
            newest[(source, category)].rating_date,
        )
        for source, category in ordered
    ]


def rating_series(player: Player, source: str, category: str) -> list[tuple[date, int]]:
    rows = HistoryRating.objects.filter(player=player, source=source, time_category=category)
    return list(rows.order_by("rating_date").values_list("rating_date", "rating"))


def pick_series(
    rows: list[RatingRow], source: str | None, category: str | None
) -> RatingRow | None:
    """The row asked for, or the first one when the request is missing or not available."""
    for row in rows:
        if (row.source, row.category) == (source, category):
            return row
    return rows[0] if rows else None


@dataclass
class Tally:
    games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0

    def add(self, result: str) -> None:
        self.games += 1
        if result == "W":
            self.wins += 1
        elif result == "D":
            self.draws += 1
        else:
            self.losses += 1

    @property
    def score_percent(self) -> int | None:
        """Points as a percentage of the games played (a win is 1, a draw is a half)."""
        if not self.games:
            return None
        return round(100 * (self.wins + self.draws / 2) / self.games)


@dataclass(frozen=True)
class OpeningRow:
    eco: str
    name: str
    tally: Tally


@dataclass(frozen=True)
class Summary:
    overall: Tally = field(default_factory=Tally)
    as_white: Tally = field(default_factory=Tally)
    as_black: Tally = field(default_factory=Tally)
    by_category: list[tuple[str, Tally]] = field(default_factory=list)
    form: list[str] = field(default_factory=list)  # newest first
    openings: list[OpeningRow] = field(default_factory=list)


def result_for(outcome: str, is_white: bool) -> str:
    """The result from one player's point of view: W, D, L, or * if the game is not over."""
    if outcome == Outcome.DRAW:
        return "D"
    if outcome == Outcome.WHITE_WINS:
        return "W" if is_white else "L"
    if outcome == Outcome.BLACK_WINS:
        return "L" if is_white else "W"
    return "*"


def summarize(player: Player, form_length: int = 10, openings: int = 5) -> Summary:
    """Results of the player's finished games."""
    games = (
        Match.objects.filter(Q(player_white=player) | Q(player_black=player))
        .exclude(outcome=Outcome.ONGOING)
        .order_by("-date", "-id")
        .values_list("player_white_id", "outcome", "time_category", "eco", "opening")
    )
    overall, as_white, as_black = Tally(), Tally(), Tally()
    by_category: dict[str, Tally] = {}
    by_opening: dict[tuple[str, str], Tally] = {}
    form: list[str] = []
    for white_id, outcome, category, eco, opening in games:
        is_white = white_id == player.pk
        result = result_for(outcome, is_white)
        overall.add(result)
        (as_white if is_white else as_black).add(result)
        by_category.setdefault(category, Tally()).add(result)
        if eco or opening:
            by_opening.setdefault((eco, opening), Tally()).add(result)
        if len(form) < form_length:
            form.append(result)

    top = sorted(by_opening.items(), key=lambda item: (-item[1].games, item[0]))[:openings]
    return Summary(
        overall=overall,
        as_white=as_white,
        as_black=as_black,
        by_category=[
            (CATEGORY_LABELS[category], by_category[category])
            for category in CATEGORY_ORDER
            if category in by_category
        ],
        form=form,
        openings=[OpeningRow(eco, name, tally) for (eco, name), tally in top],
    )


@dataclass(frozen=True)
class GameRow:
    date: date
    color: str  # "white" or "black": the colour the player had
    opponent: Player
    opponent_rating: int | None
    own_rating: int | None
    result: str
    category_label: str
    eco: str
    opening: str
    url: str


def recent_games(player: Player, limit: int = 20) -> list[GameRow]:
    matches = (
        Match.objects.filter(Q(player_white=player) | Q(player_black=player))
        .select_related("player_white", "player_black")
        .order_by("-date", "-id")[:limit]
    )
    rows = []
    for match in matches:
        is_white = match.player_white_id == player.pk
        rows.append(
            GameRow(
                date=match.date,
                color="white" if is_white else "black",
                opponent=match.player_black if is_white else match.player_white,
                opponent_rating=match.black_elo if is_white else match.white_elo,
                own_rating=match.white_elo if is_white else match.black_elo,
                result=result_for(match.outcome, is_white),
                category_label=CATEGORY_LABELS[match.time_category],
                eco=match.eco,
                opening=match.opening,
                url=f"https://lichess.org/{match.external_id}"
                if match.source == Source.LICHESS and match.external_id
                else "",
            )
        )
    return rows


def _with_fide_rating(players):
    newest_classical = (
        HistoryRating.objects.filter(
            player=OuterRef("pk"), source=Source.FIDE, time_category=TimeCategory.CLASSICAL
        )
        .order_by("-rating_date")
        .values("rating")[:1]
    )
    return players.annotate(fide_classical=Subquery(newest_classical))


def search_players(query: str, limit: int = 50):
    """Players whose name contains every word of the query, or whose FIDE id matches it."""
    words = query.split()
    if not words:
        return []
    condition = Q()
    for word in words:
        condition &= Q(name__icontains=word)
    if query.isdigit():
        condition |= Q(fide_id=int(query))
    return list(_with_fide_rating(Player.objects.filter(condition)).order_by("name")[:limit])


def top_rated(limit: int = 20) -> tuple[list[HistoryRating], date | None]:
    """The highest FIDE classical ratings in the most recent list that was imported."""
    base = HistoryRating.objects.filter(source=Source.FIDE, time_category=TimeCategory.CLASSICAL)
    latest = base.aggregate(latest=Max("rating_date"))["latest"]
    if latest is None:
        return [], None
    rows = base.filter(rating_date=latest).select_related("player")
    return list(rows.order_by("-rating", "player__name")[:limit]), latest
