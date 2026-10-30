"""Head-to-head comparison of two players: ratings side by side, results and insights."""

from dataclasses import dataclass, field

from django.db.models import Q

from core.choices import Outcome, Source, TimeCategory
from history_rating.models import HistoryRating
from matches.models import Match
from player.models import Player

from .services import CATEGORY_LABELS, SOURCE_LABELS, Tally, result_for, search_players

OTB_CATEGORIES = (TimeCategory.CLASSICAL, TimeCategory.RAPID, TimeCategory.BLITZ)
ONLINE_CATEGORIES = (TimeCategory.RAPID, TimeCategory.BLITZ)  # nobody plays classical online
ONLINE_SOURCES = (Source.CHESSCOM, Source.LICHESS)
MODES = ("todos", "presencial", "online")


def resolve_player(query: str) -> Player | None:
    """The player a search box entry most likely means: active first, then the highest rated."""
    matches = search_players(query, limit=20)
    if not matches:
        return None
    best_activity = min(player.activity for player in matches)
    candidates = [player for player in matches if player.activity == best_activity]
    return max(candidates, key=lambda player: player.fide_classical or 0)


def latest_pool_ratings(player: Player) -> dict[tuple[str, str], int]:
    """The newest rating the player has in each (source, category) pool."""
    rows = HistoryRating.objects.filter(player=player).order_by("rating_date")
    return {
        (source, category): rating
        for source, category, rating in rows.values_list("source", "time_category", "rating")
    }


@dataclass(frozen=True)
class VersusRow:
    label: str  # e.g. "Clássico"
    pool: str  # e.g. "FIDE"
    a: int | None
    b: int | None
    a_width: int  # bar lengths as percentages, so the leader's bar is the longest
    b_width: int
    leader: str | None  # "a", "b", or None when level or incomparable
    gap: int  # points between the two, 0 if either is missing


def _bar_widths(a: int | None, b: int | None) -> tuple[int, int]:
    values = [value for value in (a, b) if value is not None]
    if not values:
        return 0, 0
    top = max(values)
    base = min(values) - 150 if len(values) == 2 else top - 400
    span = top - base

    def width(value):
        return 0 if value is None else max(8, round(100 * (value - base) / span))

    return width(a), width(b)


def _row(label: str, pool: str, a: int | None, b: int | None) -> VersusRow:
    both = a is not None and b is not None
    leader = None
    if both and a != b:
        leader = "a" if a > b else "b"
    a_width, b_width = _bar_widths(a, b)
    return VersusRow(label, pool, a, b, a_width, b_width, leader, abs(a - b) if both else 0)


def build_rows(a_pool: dict, b_pool: dict) -> tuple[list[VersusRow], list[VersusRow]]:
    """(over-the-board FIDE rows, online rows). Rows where neither player has data are left out."""
    otb = []
    for category in OTB_CATEGORIES:
        a, b = a_pool.get((Source.FIDE, category)), b_pool.get((Source.FIDE, category))
        if a is not None or b is not None:
            otb.append(_row(CATEGORY_LABELS[category], SOURCE_LABELS[Source.FIDE], a, b))
    online = []
    for category in ONLINE_CATEGORIES:
        for source in ONLINE_SOURCES:
            a, b = a_pool.get((source, category)), b_pool.get((source, category))
            if a is not None or b is not None:
                online.append(_row(CATEGORY_LABELS[category], SOURCE_LABELS[source], a, b))
    return otb, online


@dataclass(frozen=True)
class MeetingRow:
    date: object
    result: str  # from player A's point of view: W, D or L
    category_label: str
    online: bool
    url: str


@dataclass(frozen=True)
class HeadToHead:
    overall: Tally = field(default_factory=Tally)
    otb: Tally = field(default_factory=Tally)
    online: Tally = field(default_factory=Tally)
    recent: list[MeetingRow] = field(default_factory=list)

    def for_mode(self, mode: str) -> Tally:
        return {"presencial": self.otb, "online": self.online}.get(mode, self.overall)


def head_to_head(a: Player, b: Player, recent: int = 5) -> HeadToHead:
    """Finished games between the two, counted from player A's point of view."""
    games = (
        Match.objects.filter(Q(player_white=a, player_black=b) | Q(player_white=b, player_black=a))
        .exclude(outcome=Outcome.ONGOING)
        .order_by("-date", "-id")
        .values_list(
            "player_white_id", "outcome", "time_category", "online", "date", "source", "external_id"
        )
    )
    overall, otb, online = Tally(), Tally(), Tally()
    meetings = []
    for white_id, outcome, category, is_online, day, source, external_id in games:
        result = result_for(outcome, white_id == a.pk)
        overall.add(result)
        (online if is_online else otb).add(result)
        if len(meetings) < recent:
            url = f"https://lichess.org/{external_id}" if source == Source.LICHESS else ""
            meetings.append(MeetingRow(day, result, CATEGORY_LABELS[category], is_online, url))
    return HeadToHead(overall, otb, online, meetings)


@dataclass(frozen=True)
class Insight:
    figure: str
    text: str


def _games(count: int) -> str:
    return f"{count} partida" if count == 1 else f"{count} partidas"


def build_insights(a: Player, b: Player, rows: list[VersusRow], h2h: HeadToHead) -> list[Insight]:
    names = {"a": a.short_name, "b": b.short_name}
    comparable = [row for row in rows if row.a is not None and row.b is not None]

    if not comparable:
        first = Insight("–", "Ainda não há ratings que se possam comparar.")
    else:
        a_leads = sum(row.leader == "a" for row in comparable)
        b_leads = sum(row.leader == "b" for row in comparable)
        if a_leads == b_leads:
            first = Insight(f"{a_leads} = {b_leads}", "Cada um lidera o mesmo número de ratings.")
        else:
            side, count = ("a", a_leads) if a_leads > b_leads else ("b", b_leads)
            text = f"ratings em que {names[side]} lidera."
            first = Insight(f"{count} de {len(comparable)}", text)

    gaps = [row for row in comparable if row.gap > 0]
    if not gaps:
        second = Insight("–", "Sem diferença de rating para destacar.")
    else:
        widest = max(gaps, key=lambda row: row.gap)
        text = (
            f"pontos de vantagem de {names[widest.leader]} no {widest.label} {widest.pool}, "
            "a maior diferença."
        )
        second = Insight(str(widest.gap), text)

    total = h2h.overall
    if total.games:
        figure = f"{total.wins}-{total.draws}-{total.losses}"
        registered = "registada" if total.games == 1 else "registadas"
        text = f"{names['a']}, empates e {names['b']}, em {_games(total.games)} {registered}."
        third = Insight(figure, text)
    else:
        third = Insight("0", "partidas entre os dois na base de dados.")
    return [first, second, third]
