"""Write Chess.com data into the database: link an account to a player, ratings and games."""

from collections.abc import Iterable
from datetime import date

from django.db import transaction

from core.choices import Source
from history_rating.models import HistoryRating
from matches.models import Match
from player.models import Platform, Player, PlayerAccount
from tournaments.models import Format, Tournament, TournamentStatus

from .chesscom import (
    ChesscomGame,
    ChesscomProfile,
    ChesscomSide,
    is_titled_tuesday,
    tournament_name,
)
from .lichess_sync import LinkError, _chosen_player


def find_account(username: str) -> PlayerAccount | None:
    return (
        PlayerAccount.objects.select_related("player")
        .filter(platform=Platform.CHESSCOM, username__iexact=username)
        .first()
    )


def link_account(
    profile: ChesscomProfile,
    *,
    fide_id: int | None = None,
    player_id: int | None = None,
    create: bool = False,
) -> tuple[PlayerAccount, str]:
    """Tie the Chess.com account to a player and return (account, how it was linked).

    Chess.com publishes the FIDE *rating* of a profile, not the FIDE id, so unlike Lichess the
    link is never guessed: it is an account that is already linked, the player the caller
    chose, or a new player (only with `create`).
    """
    account = find_account(profile.username)
    chosen = _chosen_player(fide_id, player_id)

    if account is not None:
        if chosen is not None and chosen.pk != account.player_id:
            raise LinkError(
                f"{profile.username} is already linked to {account.player}. "
                "Remove that account in the admin first if it is wrong."
            )
        player, how = account.player, "was already linked"
    elif chosen is not None:
        player, how = chosen, "as you asked"
    elif create:
        player = Player.objects.create(
            name=profile.name or profile.username,
            title=profile.title,
            women_title=profile.women_title,
        )
        how = "as a new player"
    else:
        raise LinkError(
            f"Could not tell which player {profile.username} is. Use --fide-id or --player-id "
            "to pick an existing player, or --create to add a new one."
        )

    if account is None:
        account = PlayerAccount(player=player, platform=Platform.CHESSCOM)
    account.username = profile.username
    account.external_id = str(profile.player_id) if profile.player_id else ""
    account.avatar_url = profile.avatar
    account.save()
    return account, how


def sync_ratings(player: Player, snapshot: dict, history: dict, today: date) -> int:
    """Store today's ratings plus the ratings seen in the games. Safe to repeat."""
    points = dict(history)
    for category, rating in snapshot.items():
        points[(category, today)] = rating
    rows = [
        HistoryRating(
            player=player,
            source=Source.CHESSCOM,
            time_category=category,
            rating_date=day,
            rating=rating,
        )
        for (category, day), rating in points.items()
    ]
    HistoryRating.objects.bulk_create(
        rows,
        batch_size=1000,
        update_conflicts=True,
        unique_fields=["player", "source", "time_category", "rating_date"],
        update_fields=["rating"],
    )
    return len(rows)


def _player_for(side: ChesscomSide, cache: dict[str, Player]) -> Player:
    """The player behind a Chess.com account. Unknown opponents get a minimal player."""
    key = side.username.lower()
    if key not in cache:
        account = find_account(side.username)
        if account is not None:
            cache[key] = account.player
        else:
            with transaction.atomic():
                player = Player.objects.create(name=side.username)
                PlayerAccount.objects.create(
                    player=player, platform=Platform.CHESSCOM, username=side.username
                )
            cache[key] = player
    return cache[key]


def _titled_tuesday_event(game: ChesscomGame, cache: dict[str, Tournament]) -> Tournament | None:
    """The Titled Tuesday event of a game, created on first sight (other tournaments: None)."""
    if not is_titled_tuesday(game.tournament):
        return None
    day = game.ended_at.date()
    event = cache.get(game.tournament)
    if event is None:
        event, _ = Tournament.objects.get_or_create(
            source=Source.CHESSCOM,
            external_id=game.tournament,
            defaults={
                "name": tournament_name(game.tournament),
                "format": Format.SWISS,
                "start_date": day,
                "end_date": day,
                "status": TournamentStatus.FINISHED,
            },
        )
        cache[game.tournament] = event
    first, last = min(event.start_date, day), max(event.end_date or day, day)
    if (first, last) != (event.start_date, event.end_date):
        event.start_date, event.end_date = first, last
        event.save(update_fields=["start_date", "end_date"])
    return event


def sync_games(games: Iterable[ChesscomGame]) -> tuple[int, int, int]:
    """Upsert games. Returns (new, already known, skipped). Safe to repeat."""
    new = known = skipped = 0
    players: dict[str, Player] = {}
    events: dict[str, Tournament] = {}
    for game in games:
        white, black = _player_for(game.white, players), _player_for(game.black, players)
        if white.pk == black.pk:  # two accounts of the same person
            skipped += 1
            continue
        _, created = Match.objects.update_or_create(
            source=Source.CHESSCOM,
            external_id=game.id,
            defaults={
                "player_white": white,
                "player_black": black,
                "tournament": _titled_tuesday_event(game, events),
                "outcome": game.outcome,
                "time_category": game.time_category,
                "time_base": game.time_base,
                "time_increment": game.time_increment,
                "online": True,
                "date": game.ended_at.date(),
                "pgn": game.pgn,
                "eco": game.eco,
                "opening": game.opening,
                "white_elo": game.white.rating,
                "black_elo": game.black.rating,
            },
        )
        if created:
            new += 1
        else:
            known += 1
    return new, known, skipped
