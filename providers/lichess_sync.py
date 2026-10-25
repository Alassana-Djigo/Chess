"""Write Lichess data into the database: link an account to a player, ratings and games."""

from collections.abc import Iterable
from datetime import date

from django.db import transaction

from core.choices import Source
from history_rating.models import HistoryRating
from matches.models import Match
from player.models import Platform, Player, PlayerAccount

from .lichess import LichessGame, LichessProfile, LichessSide


class LinkError(Exception):
    """The Lichess account cannot be tied to a player."""


def find_account(username: str) -> PlayerAccount | None:
    return (
        PlayerAccount.objects.select_related("player")
        .filter(platform=Platform.LICHESS, username__iexact=username)
        .first()
    )


def _chosen_player(fide_id: int | None, player_id: int | None) -> Player | None:
    if fide_id is not None:
        try:
            return Player.objects.get(fide_id=fide_id)
        except Player.DoesNotExist:
            raise LinkError(
                f"There is no player with FIDE id {fide_id}. Import the FIDE list first."
            ) from None
    if player_id is not None:
        try:
            return Player.objects.get(pk=player_id)
        except Player.DoesNotExist:
            raise LinkError(f"There is no player with id {player_id}.") from None
    return None


def link_account(
    profile: LichessProfile,
    *,
    fide_id: int | None = None,
    player_id: int | None = None,
    create: bool = False,
) -> tuple[PlayerAccount, str]:
    """Tie the Lichess account to a player and return (account, how it was linked).

    In order: an account that is already linked, the player the caller chose, the player whose
    FIDE id the user published on Lichess, and finally a new player (only with `create`).
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
    elif profile.fide_id and (known := Player.objects.filter(fide_id=profile.fide_id).first()):
        player, how = known, f"through the FIDE id {profile.fide_id} published on Lichess"
    elif create:
        player = Player.objects.create(
            name=profile.real_name or profile.username,
            fide_id=profile.fide_id,
            title=profile.title,
        )
        how = "as a new player"
    else:
        hint = ""
        if profile.fide_id:
            hint = (
                f" Lichess shows FIDE id {profile.fide_id}, but that player is not in the "
                "database yet: import the FIDE list or use --create."
            )
        raise LinkError(
            f"Could not tell which player {profile.username} is. Use --fide-id or --player-id "
            f"to pick an existing player, or --create to add a new one.{hint}"
        )

    if account is None:
        account = PlayerAccount(player=player, platform=Platform.LICHESS)
    account.username = profile.username
    account.external_id = profile.id
    account.save()
    return account, how


def sync_ratings(player: Player, profile: LichessProfile, history: dict, today: date) -> int:
    """Store the rating history plus today's current ratings. Safe to repeat."""
    points = dict(history)
    for category, rating in profile.ratings.items():
        points[(category, today)] = rating
    rows = [
        HistoryRating(
            player=player,
            source=Source.LICHESS,
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


def _player_for(side: LichessSide, cache: dict[str, Player]) -> Player:
    """The player behind a Lichess account. Unknown opponents get a minimal player of their own."""
    key = side.username.lower()
    if key not in cache:
        account = find_account(side.username)
        if account is not None:
            cache[key] = account.player
        else:
            with transaction.atomic():
                player = Player.objects.create(name=side.username, title=side.title)
                PlayerAccount.objects.create(
                    player=player,
                    platform=Platform.LICHESS,
                    username=side.username,
                    external_id=side.user_id,
                )
            cache[key] = player
    return cache[key]


def sync_games(games: Iterable[LichessGame]) -> tuple[int, int, int]:
    """Upsert games. Returns (new, already known, skipped). Safe to repeat."""
    new = known = skipped = 0
    cache: dict[str, Player] = {}
    for game in games:
        white, black = _player_for(game.white, cache), _player_for(game.black, cache)
        if white.pk == black.pk:  # two accounts of the same person
            skipped += 1
            continue
        _, created = Match.objects.update_or_create(
            source=Source.LICHESS,
            external_id=game.id,
            defaults={
                "player_white": white,
                "player_black": black,
                "outcome": game.outcome,
                "time_category": game.time_category,
                "time_base": game.time_base,
                "time_increment": game.time_increment,
                "online": True,
                "date": game.started_at.date(),
                "started_at": game.started_at,
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
