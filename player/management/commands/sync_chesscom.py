import os
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from providers.chesscom import (
    USERNAME_RE,
    ChesscomClient,
    ChesscomError,
    ChesscomNotFound,
    is_titled_tuesday,
    parse_game,
    parse_profile,
    parse_stats,
    ratings_from_games,
)
from providers.chesscom_sync import LinkError, link_account, sync_games, sync_ratings


class Command(BaseCommand):
    help = "Link a Chess.com account to a player and import its ratings and recent games."

    def add_arguments(self, parser):
        parser.add_argument("username", help="The Chess.com username.")
        parser.add_argument("--fide-id", type=int, help="Link to the player with this FIDE id.")
        parser.add_argument(
            "--player-id", type=int, help="Link to the player with this database id."
        )
        parser.add_argument(
            "--create", action="store_true", help="Create the player if none can be found."
        )
        parser.add_argument("--months", type=int, default=3, help="Recent months of games to read.")
        parser.add_argument("--no-games", action="store_true", help="Skip the games.")
        parser.add_argument("--no-ratings", action="store_true", help="Skip the ratings.")

    def make_client(self) -> ChesscomClient:
        return ChesscomClient(
            contact=os.environ.get("CHESSCOM_CONTACT", ""), notify=self.stdout.write
        )

    def handle(self, *args, **options):
        username = options["username"]
        if not USERNAME_RE.match(username):
            raise CommandError(f"'{username}' is not a valid Chess.com username.")
        if options["months"] < 1:
            raise CommandError("--months must be at least 1.")

        client = self.make_client()
        try:
            profile = parse_profile(client.get_profile(username))
        except ChesscomNotFound:
            raise CommandError(f"There is no Chess.com user called {username}.") from None
        except ChesscomError as error:
            raise CommandError(str(error)) from error
        if profile.closed:
            raise CommandError(f"The Chess.com account {profile.username} is closed.")

        try:
            with transaction.atomic():
                account, how = link_account(
                    profile,
                    fide_id=options["fide_id"],
                    player_id=options["player_id"],
                    create=options["create"],
                )
        except LinkError as error:
            raise CommandError(str(error)) from error
        player = account.player
        self.stdout.write(f"Chess.com account {profile.username} -> {player} ({how}).")

        try:
            games = []
            if not options["no_games"]:
                games = self.read_games(client, profile.username, options["months"])
                new, known, skipped = sync_games(games)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Games: {new} new, {known} already known, {skipped} skipped."
                    )
                )
                self.report_titled_tuesday(games)
            if not options["no_ratings"]:
                try:
                    snapshot = parse_stats(client.get_stats(profile.username))
                except ChesscomNotFound:
                    snapshot = {}
                history = ratings_from_games(profile.username, games)
                count = sync_ratings(player, snapshot, history, date.today())
                self.stdout.write(f"Ratings: {count} points stored.")
        except ChesscomError as error:
            raise CommandError(str(error)) from error

    def read_games(self, client, username, months):
        archives = client.get_archives(username)[-months:]
        games = []
        for url in archives:
            label = "/".join(url.rstrip("/").rsplit("/", 2)[-2:])
            self.stdout.write(f"  reading {label}...")
            games.extend(game for raw in client.get_month(url) if (game := parse_game(raw)))
        self.stdout.write(f"  {len(games)} usable games in {len(archives)} month(s).")
        return games

    def report_titled_tuesday(self, games):
        events = {game.tournament for game in games if is_titled_tuesday(game.tournament)}
        count = sum(is_titled_tuesday(game.tournament) for game in games)
        if events:
            self.stdout.write(f"Titled Tuesday: {count} games in {len(events)} event(s).")
        elif games:
            self.stdout.write(
                "Titled Tuesday: no game carries a 'titled-tuesday' tournament in this period "
                "(Chess.com may not list it by name, or there was no event)."
            )
