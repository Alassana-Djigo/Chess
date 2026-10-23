from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from player.models import Jogador

from .models import HistoryRating


class HistoryRatingAdminSearchTests(TestCase):
    """Regressao: a pesquisa no admin rebentava (FieldError) por apontar para a FK."""

    def test_search_by_player_name_finds_only_that_player(self):
        carlsen = Jogador.objects.create(
            name="Magnus Carlsen", date_birth=date(1990, 11, 30), federation="NOR", id_fide=1503014
        )
        other = Jogador.objects.create(
            name="Outro Jogador", date_birth=date(1995, 5, 5), federation="ANG", id_fide=999
        )
        for player in (carlsen, other):
            HistoryRating.objects.create(
                player=player, time_control="C", rating_date=date(2026, 1, 1), rating=2500
            )
        admin_user = get_user_model().objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(admin_user)

        response = self.client.get(
            reverse("admin:history_rating_historyrating_changelist"), {"q": "Carlsen"}
        )

        self.assertContains(response, "Magnus Carlsen")
        self.assertNotContains(response, "Outro Jogador")
