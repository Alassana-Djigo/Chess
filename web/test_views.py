from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.choices import Outcome, Source, TimeCategory
from history_rating.models import HistoryRating
from matches.models import Match
from player.models import Platform, Player, PlayerAccount


def rate(player, source, category, day, rating):
    return HistoryRating.objects.create(
        player=player, source=source, time_category=category, rating_date=day, rating=rating
    )


class HomeTests(TestCase):
    def test_empty_home_still_works(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Estatísticas de xadrez")
        self.assertContains(response, "Ainda não há ratings da FIDE importados.")

    def test_lists_the_top_fide_classical_ratings_best_first(self):
        ana = Player.objects.create(name="Silva, Ana", title="GM", federation="ANG")
        rui = Player.objects.create(name="Costa, Rui", federation="POR")
        rate(ana, Source.FIDE, TimeCategory.CLASSICAL, date(2026, 10, 1), 2700)
        rate(rui, Source.FIDE, TimeCategory.CLASSICAL, date(2026, 10, 1), 2750)

        response = self.client.get(reverse("home"))

        body = response.content.decode()
        self.assertLess(body.index("Rui Costa"), body.index("Ana Silva"))
        self.assertContains(response, "10/2026")
        self.assertContains(response, reverse("player_detail", args=[ana.pk]))
        self.assertContains(response, "2750")


class SearchTests(TestCase):
    def setUp(self):
        self.magnus = Player.objects.create(name="Carlsen, Magnus", fide_id=1503014, title="GM")
        rate(self.magnus, Source.FIDE, TimeCategory.CLASSICAL, date(2026, 10, 1), 2840)

    def test_without_a_query_it_explains_what_to_do(self):
        self.assertContains(self.client.get(reverse("player_search")), "Escreve um nome")

    def test_finds_by_name_in_any_order_and_shows_the_rating(self):
        response = self.client.get(reverse("player_search"), {"q": "magnus carlsen"})
        self.assertContains(response, "Magnus Carlsen")
        self.assertContains(response, "2840")
        self.assertContains(response, reverse("player_detail", args=[self.magnus.pk]))

    def test_finds_by_fide_id(self):
        response = self.client.get(reverse("player_search"), {"q": "1503014"})
        self.assertContains(response, "Magnus Carlsen")

    def test_no_match(self):
        response = self.client.get(reverse("player_search"), {"q": "nobody"})
        self.assertContains(response, "Nenhum jogador encontrado para «nobody».")

    def test_the_query_is_escaped_and_kept_in_the_search_box(self):
        response = self.client.get(reverse("player_search"), {"q": '"><script>alert(1)</script>'})
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_very_long_queries_are_cut(self):
        response = self.client.get(reverse("player_search"), {"q": "a" * 5000})
        self.assertEqual(response.status_code, 200)


class PlayerDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = Player.objects.create(
            name="Silva, Ana",
            title="IM",
            women_title="WGM",
            federation="ANG",
            birth_year=1995,
            fide_id=5000001,
        )
        cls.rui = Player.objects.create(name="Costa, Rui")
        PlayerAccount.objects.create(player=cls.ana, platform=Platform.LICHESS, username="ana_gm")
        PlayerAccount.objects.create(player=cls.ana, platform=Platform.CHESSCOM, username="AnaGM")
        for month, rating in ((1, 2500), (2, 2510), (3, 2520)):
            rate(cls.ana, Source.FIDE, TimeCategory.CLASSICAL, date(2026, month, 1), rating)
        rate(cls.ana, Source.LICHESS, TimeCategory.BLITZ, date(2026, 3, 1), 2900)
        Match.objects.create(
            player_white=cls.ana,
            player_black=cls.rui,
            outcome=Outcome.WHITE_WINS,
            time_category=TimeCategory.BLITZ,
            date=date(2026, 3, 2),
            eco="C20",
            opening="King's Pawn Game",
            black_elo=2750,
            source=Source.LICHESS,
            external_id="abc12345",
        )

    def get(self, **params):
        return self.client.get(reverse("player_detail", args=[self.ana.pk]), params)

    def test_shows_identity_accounts_and_ratings(self):
        response = self.get()
        self.assertContains(response, "<title>Ana Silva · Chess Stats</title>", html=False)
        self.assertContains(response, "IM")
        self.assertContains(response, "WGM")
        self.assertContains(response, "Nascido em 1995")
        self.assertContains(response, "FIDE ID 5000001")
        self.assertContains(response, "https://lichess.org/@/ana_gm")
        self.assertContains(response, "https://www.chess.com/member/AnaGM")
        self.assertContains(response, "FIDE · Clássico")
        self.assertContains(response, "Lichess · Blitz")

    def test_draws_the_chart_of_the_default_pool(self):
        response = self.get()
        self.assertEqual(response.context["selected"].source, Source.FIDE)
        self.assertEqual(response.context["chart"].count, 3)
        self.assertContains(response, '<path class="line"')

    def test_the_tab_chosen_in_the_address_changes_the_chart(self):
        response = self.get(source="lichess", category="blitz")
        self.assertEqual(response.context["selected"].source, Source.LICHESS)
        self.assertEqual(response.context["chart"].count, 1)
        self.assertNotContains(response, '<path class="line"')  # one point is only a dot
        self.assertContains(response, 'aria-current="page"')

    def test_a_bad_tab_choice_falls_back_instead_of_failing(self):
        response = self.get(source="<script>", category="nope")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected"].source, Source.FIDE)

    def test_shows_results_and_recent_games(self):
        response = self.get()
        self.assertEqual(response.context["summary"].overall.wins, 1)
        self.assertContains(response, "Aberturas mais jogadas")
        self.assertContains(response, "King&#x27;s Pawn Game")
        self.assertContains(response, "Rui Costa")
        self.assertContains(response, "(2750)")
        self.assertContains(response, "https://lichess.org/abc12345")
        self.assertContains(response, reverse("player_detail", args=[self.rui.pk]))

    def test_a_player_with_nothing_attached_gets_friendly_empty_states(self):
        lonely = Player.objects.create(name="Sem Dados")
        response = self.client.get(reverse("player_detail", args=[lonely.pk]))
        self.assertContains(response, "Ainda não há ratings para este jogador.")
        self.assertContains(response, "Ainda não há partidas terminadas para este jogador.")
        self.assertContains(response, "Ainda não há partidas para este jogador.")

    def test_the_form_line_is_worded_for_one_game_and_for_many(self):
        self.assertContains(self.get(), "Última partida")
        for day in range(1, 4):
            Match.objects.create(
                player_white=self.ana,
                player_black=self.rui,
                outcome=Outcome.DRAW,
                time_category=TimeCategory.RAPID,
                date=date(2026, 5, day),
            )
        self.assertContains(self.get(), "Últimas 4 partidas")

    def test_unknown_player_is_a_404(self):
        self.assertEqual(self.client.get(reverse("player_detail", args=[999999])).status_code, 404)

    def test_names_cannot_inject_html(self):
        evil = Player.objects.create(name="<script>alert(1)</script>, <b>x</b>")
        response = self.client.get(reverse("player_detail", args=[evil.pk]))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertNotContains(response, "<b>x</b>")
        self.assertContains(response, "&lt;b&gt;x&lt;/b&gt;")

    def test_the_number_of_queries_does_not_grow_with_the_games(self):
        def count_queries():
            with CaptureQueriesContext(connection) as queries:
                self.get()
            return len(queries)

        before = count_queries()
        for day in range(1, 15):
            Match.objects.create(
                player_white=self.rui,
                player_black=self.ana,
                outcome=Outcome.DRAW,
                time_category=TimeCategory.RAPID,
                date=date(2026, 4, day),
            )
        self.assertEqual(count_queries(), before)
        self.assertLessEqual(before, 12)
