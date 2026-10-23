from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.choices import Outcome, Source, TimeCategory
from player.models import Player

from .models import Match


class MatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.white = Player.objects.create(name="Ana", federation="ANG")
        cls.black = Player.objects.create(name="Rui", federation="ANG")

    def make_match(self, **overrides):
        data = {
            "player_white": self.white,
            "player_black": self.black,
            "time_category": TimeCategory.CLASSICAL,
            "date": date(2026, 7, 1),
            "outcome": Outcome.DRAW,
        }
        data.update(overrides)
        return Match.objects.create(**data)

    def test_str_shows_players_and_date(self):
        match = self.make_match()
        self.assertEqual(str(match), "Ana vs Rui - 2026-07-01")
        self.assertFalse(match.online)

    def test_new_match_is_in_progress_by_default(self):
        match = Match.objects.create(
            player_white=self.white,
            player_black=self.black,
            time_category=TimeCategory.BLITZ,
            date=date(2026, 7, 1),
        )
        self.assertEqual(match.outcome, Outcome.ONGOING)

    def test_a_player_cannot_play_themselves(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_match(player_black=self.white)

    def test_optional_details_are_stored(self):
        match = self.make_match(
            pgn="1. e4 e5 *",
            eco="C20",
            opening="King's Pawn Game",
            white_elo=2500,
            black_elo=2480,
            time_base=5400,
            time_increment=30,
            round=3,
            board=1,
        )
        match.refresh_from_db()
        self.assertEqual((match.eco, match.white_elo, match.time_base), ("C20", 2500, 5400))

    def test_invalid_eco_code_is_rejected(self):
        match = self.make_match(eco="Z99")
        with self.assertRaises(ValidationError) as caught:
            match.full_clean()
        self.assertIn("eco", caught.exception.message_dict)

    def test_source_and_external_id_cannot_repeat(self):
        self.make_match(source=Source.LICHESS, external_id="g1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_match(source=Source.LICHESS, external_id="g1")

    def test_matches_are_listed_newest_first(self):
        old = self.make_match(date=date(2026, 1, 1))
        new = self.make_match(date=date(2026, 8, 1))
        self.assertEqual(list(Match.objects.all()), [new, old])
