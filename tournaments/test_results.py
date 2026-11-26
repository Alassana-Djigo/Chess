from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from player.models import Player

from .models import Format, Tournament, TournamentResult


class TournamentResultTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(
            name="Titled Tuesday", format=Format.SWISS, start_date=date(2026, 11, 3)
        )
        self.player = Player.objects.create(name="Nakamura, Hikaru")

    def result(self, **kwargs):
        data = {
            "tournament": self.tournament,
            "player": self.player,
            "points": Decimal("9.5"),
            "placement": 2,
        }
        data.update(kwargs)
        return TournamentResult.objects.create(**data)

    def test_str(self):
        self.assertEqual(str(self.result()), "Nakamura, Hikaru 9.5 in Titled Tuesday")

    def test_a_player_has_one_result_per_tournament(self):
        self.result()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.result(points=Decimal("1"))

    def test_results_are_ordered_by_placement(self):
        other = Player.objects.create(name="Other")
        self.result()
        self.result(player=other, points=Decimal("10"), placement=1)
        self.assertEqual([r.placement for r in self.tournament.results.all()], [1, 2])

    def test_deleting_a_tournament_deletes_its_results_but_a_player_is_protected(self):
        self.result()
        with self.assertRaises(ProtectedError):
            self.player.delete()
        self.tournament.delete()
        self.assertEqual(TournamentResult.objects.count(), 0)
