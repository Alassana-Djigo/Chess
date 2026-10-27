from datetime import date

from django.test import TestCase
from django.urls import reverse

from core.choices import Source, TimeCategory
from history_rating.models import HistoryRating
from player.models import Player

from .services import historic_players, search_players, top_rated


def rate(
    player, rating, source=Source.FIDE, category=TimeCategory.CLASSICAL, day=date(2026, 10, 1)
):
    return HistoryRating.objects.create(
        player=player, source=source, time_category=category, rating_date=day, rating=rating
    )


class ActiveVersusInactiveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active = Player.objects.create(name="Activo, Ana", is_active=True)
        cls.unknown = Player.objects.create(name="Desconhecido, Dino")
        cls.retired = Player.objects.create(name="Reformado, Rui", is_active=False, title="GM")
        for player, rating in ((cls.active, 2700), (cls.unknown, 2650), (cls.retired, 2800)):
            rate(player, rating)

    def test_top_list_hides_inactive_players(self):
        rows, _ = top_rated()
        self.assertEqual([r.player for r in rows], [self.active, self.unknown])

    def test_search_puts_active_first_and_inactive_last(self):
        found = search_players("o")  # every name has an "o"
        self.assertEqual(found, [self.active, self.unknown, self.retired])

    def test_inactive_players_are_still_found_by_name(self):
        self.assertEqual(search_players("reformado"), [self.retired])

    def test_historic_list_has_only_inactive_players(self):
        self.assertEqual(list(historic_players()), [self.retired])

    def test_historic_list_is_sorted_by_best_classical_rating_then_name(self):
        high = Player.objects.create(name="Alto, Hugo", is_active=False)
        none = Player.objects.create(name="Sem Rating, Zé", is_active=False)
        rate(high, 2900)
        rate(high, 2950, day=date(2026, 9, 1))
        rate(none, 2999, source=Source.LICHESS)  # other pool: not a FIDE classical rating
        ranked = list(historic_players())
        self.assertEqual(ranked, [high, self.retired, none])
        self.assertEqual(ranked[0].peak_classical, 2950)
        self.assertIsNone(ranked[2].peak_classical)

    def test_the_home_page_shows_active_players_only(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Ana Activo")
        self.assertContains(response, "Dino Desconhecido")
        self.assertNotContains(response, "Rui Reformado")
        self.assertContains(response, reverse("historic_players"))  # the navigation link

    def test_the_player_page_says_when_a_player_is_inactive(self):
        retired = self.client.get(reverse("player_detail", args=[self.retired.pk]))
        active = self.client.get(reverse("player_detail", args=[self.active.pk]))
        self.assertContains(retired, "Inactivo na FIDE")
        self.assertNotContains(active, "Inactivo na FIDE")


class HistoricPageTests(TestCase):
    def test_empty_state(self):
        response = self.client.get(reverse("historic_players"))
        self.assertContains(response, "Todos os tempos")
        self.assertContains(response, "Ainda não há jogadores inactivos")

    def test_lists_the_inactive_players_with_their_best_rating(self):
        retired = Player.objects.create(name="Reformado, Rui", is_active=False, title="GM")
        rate(retired, 2800)
        Player.objects.create(name="Activo, Ana", is_active=True)

        response = self.client.get(reverse("historic_players"))

        self.assertContains(response, "Rui Reformado")
        self.assertContains(response, "2800")
        self.assertNotContains(response, "Ana Activo")

    def test_pages_of_fifty(self):
        for i in range(51):
            Player.objects.create(name=f"Inactivo {i:02d}", is_active=False)
        first = self.client.get(reverse("historic_players"))
        second = self.client.get(reverse("historic_players"), {"page": 2})
        self.assertContains(first, "Página 1 de 2")
        self.assertContains(first, "Seguinte")
        self.assertNotContains(first, "Anterior")
        self.assertContains(second, "Anterior")
        self.assertEqual(len(second.context["page"].object_list), 1)

    def test_a_bad_page_number_does_not_break_the_page(self):
        Player.objects.create(name="Inactivo", is_active=False)
        for value in ("abc", "-3", "999"):
            with self.subTest(page=value):
                response = self.client.get(reverse("historic_players"), {"page": value})
                self.assertEqual(response.status_code, 200)
