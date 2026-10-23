from datetime import date

from django.test import TestCase

from player.models import Jogador

from .models import Match


class MatchTests(TestCase):
    def test_str_shows_players_and_date(self):
        white = Jogador.objects.create(name="Ana", date_birth=date(2000, 1, 1), federation="ANG")
        black = Jogador.objects.create(name="Rui", date_birth=date(2001, 1, 1), federation="ANG")
        match = Match.objects.create(
            player_white=white,
            player_black=black,
            outcome="1/2-1/2",
            time_control="C",
            date=date(2026, 7, 1),
        )
        self.assertEqual(str(match), "Ana vs Rui - 2026-07-01")
        self.assertFalse(match.online)
