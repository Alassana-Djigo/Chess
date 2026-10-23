from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from core.choices import Source, TimeCategory
from player.models import Player

from .models import HistoryRating


def make_rating(player, **overrides):
    data = {
        "player": player,
        "source": Source.FIDE,
        "time_category": TimeCategory.CLASSICAL,
        "rating_date": date(2026, 1, 1),
        "rating": 2830,
    }
    data.update(overrides)
    return HistoryRating.objects.create(**data)


class HistoryRatingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.player = Player.objects.create(name="Magnus Carlsen", federation="NOR", fide_id=1503014)

    def test_str(self):
        rating = make_rating(self.player)
        self.assertEqual(str(rating), "Magnus Carlsen - 2026-01-01: 2830")

    def test_one_rating_per_player_source_category_and_date(self):
        make_rating(self.player)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_rating(self.player, rating=2835)

    def test_same_date_is_allowed_across_sources(self):
        make_rating(self.player, source=Source.FIDE)
        make_rating(self.player, source=Source.LICHESS, rating=3100)
        self.assertEqual(HistoryRating.objects.count(), 2)

    def test_same_date_is_allowed_across_time_categories(self):
        make_rating(self.player, time_category=TimeCategory.CLASSICAL)
        make_rating(self.player, time_category=TimeCategory.BLITZ, rating=2880)
        self.assertEqual(HistoryRating.objects.count(), 2)


class HistoryRatingAdminSearchTests(TestCase):
    """Regressao: a pesquisa no admin rebentava (FieldError) por apontar para a FK."""

    def test_search_by_player_name_finds_only_that_player(self):
        carlsen = Player.objects.create(name="Magnus Carlsen", federation="NOR", fide_id=1503014)
        other = Player.objects.create(name="Outro Jogador", federation="ANG", fide_id=999)
        make_rating(carlsen, rating=2830)
        make_rating(other, rating=2500)
        admin_user = get_user_model().objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(admin_user)

        response = self.client.get(
            reverse("admin:history_rating_historyrating_changelist"), {"q": "Carlsen"}
        )

        self.assertContains(response, "Magnus Carlsen")
        self.assertNotContains(response, "Outro Jogador")
