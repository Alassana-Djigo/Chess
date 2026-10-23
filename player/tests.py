from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Jogador


def make_player(**overrides):
    data = {"name": "Magnus Carlsen", "date_birth": date(1990, 11, 30), "federation": "NOR"}
    data.update(overrides)
    return Jogador.objects.create(**data)


class JogadorTests(TestCase):
    def test_defaults_and_str(self):
        player = make_player()
        self.assertEqual(player.title, "X")
        self.assertEqual(str(player), "Magnus Carlsen")

    def test_fide_id_must_be_unique(self):
        make_player(id_fide=1503014)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_player(name="Outro", id_fide=1503014)

    def test_players_without_fide_id_can_coexist(self):
        make_player(name="Sem FIDE 1")
        make_player(name="Sem FIDE 2")
        self.assertEqual(Jogador.objects.filter(id_fide__isnull=True).count(), 2)
