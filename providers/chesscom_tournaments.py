"""Write Chess.com tournament results into the database."""

from django.db.models.functions import Lower

from core.choices import Source
from player.models import Platform, Player, PlayerAccount
from tournaments.models import Format, Tournament, TournamentResult, TournamentStatus

from .chesscom import ChesscomEvent, ChesscomStanding, tournament_name


def upsert_event(slug: str, event: ChesscomEvent) -> Tournament:
    """Create or refresh the Tournament of an event that has a known start day."""
    end = max(event.end or event.start, event.start)
    status = TournamentStatus.FINISHED if event.status == "finished" else TournamentStatus.ONGOING
    values = {
        "name": tournament_name(slug),
        "format": Format.SWISS,
        "start_date": event.start,
        "end_date": end,
        "rounds": event.rounds,
        "status": status,
    }
    tournament, created = Tournament.objects.get_or_create(
        source=Source.CHESSCOM, external_id=slug, defaults=values
    )
    if not created:
        for field, value in values.items():
            setattr(tournament, field, value)
        tournament.save(update_fields=list(values))
    return tournament


def _players_for(usernames: dict[str, ChesscomStanding]) -> dict[str, int]:
    """player id for each (lowercase) username; unknown accounts get a minimal player."""
    accounts = (
        PlayerAccount.objects.filter(platform=Platform.CHESSCOM)
        .annotate(key=Lower("username"))
        .filter(key__in=list(usernames))
    )
    found = {account.key: account.player_id for account in accounts}
    missing = [name for name in usernames if name not in found]
    created = Player.objects.bulk_create([Player(name=usernames[n].username) for n in missing])
    PlayerAccount.objects.bulk_create(
        [
            PlayerAccount(
                player=player, platform=Platform.CHESSCOM, username=usernames[name].username
            )
            for name, player in zip(missing, created, strict=True)
        ]
    )
    found.update({name: player.pk for name, player in zip(missing, created, strict=True)})
    return found


def sync_standings(tournament: Tournament, standings: list[ChesscomStanding]) -> int:
    """Store the final standings (placement by points only). Safe to repeat. Returns the count."""
    by_username = {standing.username.lower(): standing for standing in standings}
    player_ids = _players_for(by_username)

    best: dict[int, ChesscomStanding] = {}  # two accounts of one person: keep the better score
    for name, standing in by_username.items():
        pid = player_ids[name]
        if pid not in best or standing.points > best[pid].points:
            best[pid] = standing

    scores = [standing.points for standing in best.values()]
    rows = [
        TournamentResult(
            tournament=tournament,
            player_id=pid,
            points=standing.points,
            placement=1 + sum(other > standing.points for other in scores),
            is_winner=standing.is_winner,
        )
        for pid, standing in best.items()
    ]
    TournamentResult.objects.bulk_create(
        rows,
        batch_size=500,
        update_conflicts=True,
        unique_fields=["tournament", "player"],
        update_fields=["points", "placement", "is_winner"],
    )
    return len(rows)
