from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from core.choices import Source
from history_rating.models import HistoryRating
from matches.models import Match

from .chesscom import ChesscomClient, ChesscomNotFound
from .testing import FakeResponse, FakeSession
from .testing_chesscom import chesscom_profile

ARCHIVES = "https://api.chess.com/pub/player/anagm/games/archives"


class NotFoundMessageTests(SimpleTestCase):
    def test_the_message_says_what_happened_and_where(self):
        for status in (404, 410):
            with self.subTest(status=status):
                client = ChesscomClient(session=FakeSession(FakeResponse(status_code=status)))
                with self.assertRaises(ChesscomNotFound) as caught:
                    client.get_archives("AnaGM")
                message = str(caught.exception)
                self.assertIn(f"answered {status} (not found)", message)
                self.assertIn(ARCHIVES, message)


class FakeWithoutArchives:
    def get_profile(self, username):
        return chesscom_profile()

    def get_stats(self, username):
        return {"chess_blitz": {"last": {"rating": 3000}}}

    def get_archives(self, username):
        raise ChesscomNotFound(ARCHIVES)


class MissingArchiveTests(TestCase):
    def test_without_an_archive_list_the_ratings_are_still_stored(self):
        out = StringIO()
        target = "player.management.commands.sync_chesscom.ChesscomClient"
        with mock.patch(target, return_value=FakeWithoutArchives()):
            call_command("sync_chesscom", "AnaGM", "--create", stdout=out)

        output = out.getvalue()
        self.assertIn("has no game archive for AnaGM", output)
        self.assertIn("ratings will still be stored", output)
        self.assertIn("Games: 0 new, 0 already known, 0 skipped.", output)
        self.assertEqual(Match.objects.count(), 0)
        rating = HistoryRating.objects.get(source=Source.CHESSCOM)
        self.assertEqual((rating.time_category, rating.rating), ("blitz", 3000))
