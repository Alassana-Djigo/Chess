import os
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from providers.lichess import (
    USERNAME_RE,
    LichessClient,
    LichessError,
    LichessNotFound,
    parse_game,
    parse_profile,
    parse_rating_history,
)
from providers.lichess_sync import LinkError, link_account, sync_games, sync_ratings


class Command(BaseCommand):
    help = "Link a Lichess account to a player and import its ratings and recent games."

    def add_arguments(self, parser):
        parser.add_argument("username", help="The Lichess username.")
        parser.add_argument("--fide-id", type=int, help="Link to the player with this FIDE id.")
        parser.add_argument(
            "--player-id", type=int, help="Link to the player with this database id."
        )
        parser.add_argument(
            "--create", action="store_true", help="Create the player if none can be found."
        )
        parser.add_argument("--max-games", type=int, default=30, help="Recent games to import.")
        parser.add_argument("--no-games", action="store_true", help="Skip the games.")
        parser.add_argument("--no-ratings", action="store_true", help="Skip the ratings.")

    def make_client(self) -> LichessClient:
        token = os.environ.get("LICHESS_API_TOKEN", "")
        return LichessClient(token=token, notify=self.stdout.write)

    def handle(self, *args, **options):
        username = options["username"]
        if not USERNAME_RE.match(username):
            raise CommandError(f"'{username}' is not a valid Lichess username.")
        if options["max_games"] < 1:
            raise CommandError("--max-games must be at least 1.")

        client = self.make_client()
        try:
            profile = parse_profile(client.get_user(username))
        except LichessNotFound:
            raise CommandError(f"There is no Lichess user called {username}.") from None
        except LichessError as error:
            raise CommandError(str(error)) from error
        if profile.closed:
            raise CommandError(f"The Lichess account {profile.username} is closed.")

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
        self.stdout.write(f"Lichess account {profile.username} -> {player} ({how}).")

        try:
            if not options["no_ratings"]:
                history = parse_rating_history(client.get_rating_history(profile.username))
                count = sync_ratings(player, profile, history, date.today())
                note = "" if history else " (Lichess sent no history; see LICHESS_API_TOKEN)"
                self.stdout.write(f"Ratings: {count} points stored{note}.")
            if not options["no_games"]:
                games, ignored = [], 0
                for raw in client.iter_games(profile.username, options["max_games"]):
                    game = parse_game(raw)
                    if game is None:
                        ignored += 1
                    else:
                        games.append(game)
                new, known, skipped = sync_games(games)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Games: {new} new, {known} already known, {ignored + skipped} ignored."
                    )
                )
        except LichessError as error:
            raise CommandError(str(error)) from error
