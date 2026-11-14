from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from matches.models import Match
from player.models import PlayerAccount

from .chesscom import (
    ChesscomClient,
    ChesscomError,
    ChesscomForbidden,
    ChesscomRateLimited,
)
from .testing import FakeResponse, FakeSession
from .testing_chesscom import chesscom_game, chesscom_profile

MONTH_URL = "https://api.chess.com/pub/player/anagm/games/{}/{:02d}"


def month(year, number):
    return MONTH_URL.format(year, number)


class ForbiddenTests(SimpleTestCase):
    def make_client(self, *responses):
        self.sleeps, self.notes = [], []
        session = FakeSession(*responses)
        client = ChesscomClient(session=session, sleep=self.sleeps.append, notify=self.notes.append)
        return client, session

    def test_a_forbidden_error_is_a_chesscom_error(self):
        self.assertTrue(issubclass(ChesscomForbidden, ChesscomError))

    def test_a_temporary_403_is_retried_after_a_pause(self):
        client, session = self.make_client(
            FakeResponse(status_code=403), FakeResponse(payload={"ok": 1})
        )
        self.assertEqual(client.get_profile("AnaGM"), {"ok": 1})
        self.assertEqual(self.sleeps, [5])
        self.assertEqual(len(session.calls), 2)
        self.assertIn("403", self.notes[0])

    def test_a_persistent_403_gives_a_helpful_error(self):
        client, session = self.make_client(*[FakeResponse(status_code=403)] * 3)
        with self.assertRaises(ChesscomForbidden) as caught:
            client.get_profile("AnaGM")
        self.assertIn("try again later", str(caught.exception))
        self.assertEqual(self.sleeps, [5, 5])
        self.assertEqual(len(session.calls), 3)

    def test_a_short_pause_separates_consecutive_months(self):
        client, _ = self.make_client(*[FakeResponse(payload={"games": []})] * 3)
        for number in (8, 9, 10):
            client.get_month(month(2025, number))
        self.assertEqual(self.sleeps, [1.0, 1.0])  # none before the first month


class FakeChesscom:
    """Stands in for ChesscomClient. Each archive holds games, or an exception to raise."""

    def __init__(self, profile, archives):
        self.profile, self.archives = profile, archives

    def get_profile(self, username):
        return self.profile

    def get_stats(self, username):
        return {}

    def get_archives(self, username):
        return list(self.archives)

    def get_month(self, url):
        value = self.archives[url]
        if isinstance(value, Exception):
            raise value
        return value


class SkippedMonthsTests(TestCase):
    def run_command(self, fake, *args):
        out = StringIO()
        target = "player.management.commands.sync_chesscom.ChesscomClient"
        with mock.patch(target, return_value=fake):
            call_command("sync_chesscom", "AnaGM", "--create", *args, stdout=out)
        return out.getvalue()

    def forbidden(self, url):
        return ChesscomForbidden(f"Chess.com answered 403 (Forbidden) for {url}.")

    def test_a_month_that_fails_is_skipped_and_the_others_are_kept(self):
        bad = month(2025, 11)
        fake = FakeChesscom(
            chesscom_profile(),
            {
                month(2025, 9): [chesscom_game("a")],
                month(2025, 10): [chesscom_game("b")],
                bad: self.forbidden(bad),
            },
        )
        output = self.run_command(fake)

        self.assertIn("skipped 2025/11", output)
        self.assertIn("Skipped 1 month(s): 2025/11. Run the command again later", output)
        self.assertIn("2 usable games in 2 month(s).", output)
        self.assertIn("Games: 2 new", output)
        self.assertEqual(Match.objects.count(), 2)

    def test_when_every_month_fails_it_is_an_error_and_the_link_stays(self):
        urls = [month(2025, 10), month(2025, 11)]
        fake = FakeChesscom(chesscom_profile(), {url: self.forbidden(url) for url in urls})
        with self.assertRaisesMessage(CommandError, "Could not read any of the 2 month(s)"):
            self.run_command(fake)
        self.assertTrue(PlayerAccount.objects.filter(username="AnaGM").exists())

    def test_hitting_the_rate_limit_stops_everything(self):
        fake = FakeChesscom(
            chesscom_profile(),
            {
                month(2025, 10): ChesscomRateLimited("slow down"),
                month(2025, 11): [chesscom_game("a")],
            },
        )
        with self.assertRaisesMessage(CommandError, "slow down"):
            self.run_command(fake)
        self.assertEqual(Match.objects.count(), 0)

    def test_it_says_whether_the_profile_has_a_photo(self):
        fake = FakeChesscom(chesscom_profile(), {})
        self.assertIn("Photo: saved.", self.run_command(fake, "--no-games"))
        PlayerAccount.objects.all().delete()
        bare = FakeChesscom(chesscom_profile(avatar=""), {})
        self.assertIn(
            "Photo: none on this Chess.com profile.", self.run_command(bare, "--no-games")
        )
