from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from core.choices import Source

from .models import Format, Tournament, TournamentStatus


def make_tournament(**overrides):
    data = {
        "name": "Test Open",
        "format": Format.SWISS,
        "start_date": date(2026, 7, 1),
        "end_date": date(2026, 7, 9),
    }
    data.update(overrides)
    return Tournament.objects.create(**data)


class TournamentTests(TestCase):
    def test_defaults_and_str(self):
        tournament = make_tournament()
        self.assertEqual(tournament.status, TournamentStatus.SCHEDULED)
        self.assertEqual(tournament.source, Source.MANUAL)
        self.assertIsNone(tournament.rounds)
        self.assertIsNone(tournament.prize)
        self.assertEqual(str(tournament), "Test Open")

    def test_end_date_is_optional_while_ongoing(self):
        tournament = make_tournament(end_date=None, status=TournamentStatus.ONGOING)
        self.assertIsNone(tournament.end_date)

    def test_end_date_cannot_precede_start_date(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_tournament(end_date=date(2026, 6, 30))

    def test_source_and_external_id_cannot_repeat(self):
        make_tournament(source=Source.LICHESS, external_id="abc123")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_tournament(name="Outro", source=Source.LICHESS, external_id="abc123")

    def test_same_external_id_is_allowed_across_sources(self):
        make_tournament(source=Source.LICHESS, external_id="abc123")
        make_tournament(name="Outro", source=Source.FIDE, external_id="abc123")
        self.assertEqual(Tournament.objects.count(), 2)

    def test_blank_external_id_can_repeat(self):
        make_tournament(name="Manual 1")
        make_tournament(name="Manual 2")
        self.assertEqual(Tournament.objects.count(), 2)
