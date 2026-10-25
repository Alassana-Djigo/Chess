from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from core.choices import Source
from history_rating.models import HistoryRating
from matches.models import Match
from player.models import Platform, Player, PlayerAccount

from .lichess import LichessError, LichessNotFound, LichessRateLimited
from .testing import lichess_game, lichess_user


class FakeLichess:
    def __init__(self, user=None, history=(), games=(), error=None):
        self.user, self.history, self.games, self.error = user, list(history), list(games), error
        self.requested_games = None

    def get_user(self, username):
        if self.user is None:
            raise LichessNotFound(username)
        return self.user

    def get_rating_history(self, username):
        if self.error:
            raise self.error
        return self.history

    def iter_games(self, username, max_games):
        self.requested_games = max_games
        if self.error:
            raise self.error
        yield from self.games


class SyncLichessCommandTests(TestCase):
    command_module = "player.management.commands.sync_lichess"

    def run_command(self, fake, *args):
        from unittest import mock

        out = StringIO()
        with mock.patch(f"{self.command_module}.LichessClient", return_value=fake):
            call_command("sync_lichess", *args, stdout=out)
        return out.getvalue()

    def anna(self, **kwargs):
        return FakeLichess(
            user=lichess_user("Anna", **kwargs),
            history=[{"name": "blitz", "points": [[2026, 8, 1, 2100]]}],
            games=[lichess_game("g1"), lichess_game("g2", winner=None, status="aborted")],
        )

    def test_links_by_fide_id_and_imports_ratings_and_games(self):
        ana = Player.objects.create(name="Silva, Ana", fide_id=5000001)

        output = self.run_command(self.anna(), "Anna", "--fide-id", "5000001")

        self.assertIn("Lichess account Anna -> Silva, Ana (as you asked)", output)
        self.assertIn("Ratings: 3 points stored.", output)
        self.assertIn("Games: 1 new, 0 already known, 1 ignored.", output)
        self.assertEqual(PlayerAccount.objects.get(username="Anna").player, ana)
        self.assertEqual(HistoryRating.objects.filter(source=Source.LICHESS).count(), 3)
        self.assertEqual(Match.objects.filter(source=Source.LICHESS).count(), 1)

    def test_links_through_the_fide_id_published_on_lichess(self):
        Player.objects.create(name="Silva, Ana", fide_id=5000001)
        output = self.run_command(self.anna(fide_id=5000001), "Anna")
        self.assertIn("published on Lichess", output)

    def test_create_adds_a_new_player(self):
        self.run_command(self.anna(real_name="Ana Silva"), "Anna", "--create")
        self.assertTrue(Player.objects.filter(name="Ana Silva").exists())

    def test_running_twice_is_safe(self):
        Player.objects.create(name="Silva, Ana", fide_id=5000001)
        self.run_command(self.anna(), "Anna", "--fide-id", "5000001")
        output = self.run_command(self.anna(), "Anna")

        self.assertIn("was already linked", output)
        self.assertIn("Games: 0 new, 1 already known", output)
        self.assertEqual(Match.objects.count(), 1)
        self.assertEqual(HistoryRating.objects.count(), 3)

    def test_flags_skip_ratings_and_games(self):
        self.run_command(self.anna(), "Anna", "--create", "--no-ratings", "--no-games")
        self.assertEqual(HistoryRating.objects.count(), 0)
        self.assertEqual(Match.objects.count(), 0)

    def test_max_games_is_passed_on(self):
        fake = self.anna()
        self.run_command(fake, "Anna", "--create", "--max-games", "7")
        self.assertEqual(fake.requested_games, 7)

    def test_says_so_when_lichess_sends_no_history(self):
        fake = FakeLichess(user=lichess_user("Anna"))
        output = self.run_command(fake, "Anna", "--create", "--no-games")
        self.assertIn("Lichess sent no history; see LICHESS_API_TOKEN", output)

    def test_unknown_user(self):
        with self.assertRaisesMessage(CommandError, "no Lichess user called Nobody"):
            self.run_command(FakeLichess(), "Nobody", "--create")

    def test_closed_account(self):
        fake = FakeLichess(user=lichess_user("Anna", disabled=True))
        with self.assertRaisesMessage(CommandError, "is closed"):
            self.run_command(fake, "Anna", "--create")

    def test_without_a_target_it_explains_the_options(self):
        with self.assertRaisesMessage(CommandError, "--fide-id"):
            self.run_command(self.anna(), "Anna")
        self.assertEqual(PlayerAccount.objects.count(), 0)

    def test_invalid_username_and_max_games(self):
        with self.assertRaisesMessage(CommandError, "not a valid Lichess username"):
            self.run_command(self.anna(), "../etc")
        with self.assertRaisesMessage(CommandError, "at least 1"):
            self.run_command(self.anna(), "Anna", "--create", "--max-games", "0")

    def test_lichess_problems_become_clear_errors(self):
        fake = FakeLichess(user=lichess_user("Anna"), error=LichessRateLimited("slow down"))
        with self.assertRaisesMessage(CommandError, "slow down"):
            self.run_command(fake, "Anna", "--create")

    def test_the_account_stays_linked_if_the_games_fail(self):
        fake = FakeLichess(user=lichess_user("Anna"), error=LichessError("cut"))
        fake.get_rating_history = lambda username: []
        with self.assertRaises(CommandError):
            self.run_command(fake, "Anna", "--create")
        self.assertTrue(
            PlayerAccount.objects.filter(platform=Platform.LICHESS, username="Anna").exists()
        )
