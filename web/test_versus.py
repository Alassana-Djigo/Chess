from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.choices import Outcome, Source, TimeCategory
from history_rating.models import HistoryRating
from matches.models import Match
from player.models import Player

from .versus import (
    build_insights,
    build_rows,
    head_to_head,
    latest_pool_ratings,
    resolve_player,
)

CLASSICAL, RAPID, BLITZ, BULLET = (
    TimeCategory.CLASSICAL,
    TimeCategory.RAPID,
    TimeCategory.BLITZ,
    TimeCategory.BULLET,
)


def rate(player, source, category, rating, day=date(2026, 10, 1)):
    return HistoryRating.objects.create(
        player=player, source=source, time_category=category, rating_date=day, rating=rating
    )


class ResolvePlayerTests(TestCase):
    def test_no_match(self):
        self.assertIsNone(resolve_player("nobody"))

    def test_finds_by_name_and_by_fide_id(self):
        magnus = Player.objects.create(name="Carlsen, Magnus", fide_id=1503014, is_active=True)
        self.assertEqual(resolve_player("magnus carlsen"), magnus)
        self.assertEqual(resolve_player("1503014"), magnus)

    def test_active_players_beat_inactive_ones(self):
        Player.objects.create(name="Nakamura, Old", is_active=False)
        active = Player.objects.create(name="Nakamura, Hikaru", is_active=True)
        self.assertEqual(resolve_player("nakamura"), active)

    def test_among_active_players_the_highest_rated_wins(self):
        low = Player.objects.create(name="Silva, Ana", is_active=True)
        high = Player.objects.create(name="Silva, Rui", is_active=True)
        rate(low, Source.FIDE, CLASSICAL, 2300)
        rate(high, Source.FIDE, CLASSICAL, 2650)
        self.assertEqual(resolve_player("silva"), high)


class RatingRowsTests(TestCase):
    def test_latest_rating_per_pool(self):
        player = Player.objects.create(name="Ana")
        rate(player, Source.FIDE, CLASSICAL, 2500, day=date(2026, 8, 1))
        rate(player, Source.FIDE, CLASSICAL, 2520, day=date(2026, 9, 1))
        self.assertEqual(latest_pool_ratings(player), {(Source.FIDE, CLASSICAL): 2520})

    def test_over_the_board_rows_are_the_three_fide_ratings(self):
        a = {(Source.FIDE, CLASSICAL): 2830, (Source.FIDE, RAPID): 2790, (Source.FIDE, BLITZ): 2840}
        b = {(Source.FIDE, CLASSICAL): 2800, (Source.FIDE, RAPID): 2810}
        otb, online = build_rows(a, b)
        self.assertEqual([r.label for r in otb], ["Clássico", "Rápido", "Blitz"])
        self.assertEqual(online, [])
        self.assertEqual((otb[0].leader, otb[0].gap), ("a", 30))
        self.assertEqual((otb[1].leader, otb[1].gap), ("b", 20))
        self.assertEqual((otb[2].a, otb[2].b, otb[2].leader, otb[2].gap), (2840, None, None, 0))

    def test_online_rows_have_no_classical_and_no_bullet(self):
        both = {
            (Source.CHESSCOM, CLASSICAL): 2000,
            (Source.CHESSCOM, BULLET): 3000,
            (Source.CHESSCOM, RAPID): 2700,
            (Source.LICHESS, BLITZ): 3100,
        }
        _, online = build_rows(both, both)
        self.assertEqual(
            [(r.label, r.pool) for r in online], [("Rápido", "Chess.com"), ("Blitz", "Lichess")]
        )

    def test_rows_without_data_for_either_player_are_left_out(self):
        self.assertEqual(build_rows({}, {}), ([], []))

    def test_a_tie_has_no_leader(self):
        pool = {(Source.FIDE, CLASSICAL): 2700}
        otb, _ = build_rows(pool, pool)
        self.assertEqual((otb[0].leader, otb[0].gap), (None, 0))

    def test_the_leader_gets_the_longest_bar(self):
        otb, _ = build_rows({(Source.FIDE, CLASSICAL): 2830}, {(Source.FIDE, CLASSICAL): 2800})
        row = otb[0]
        self.assertEqual(row.a_width, 100)
        self.assertTrue(8 <= row.b_width < 100)

    def test_a_missing_rating_has_no_bar(self):
        otb, _ = build_rows({(Source.FIDE, BLITZ): 2800}, {})
        self.assertEqual((otb[0].a_width, otb[0].b_width), (100, 0))


class HeadToHeadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Player.objects.create(name="Carlsen, Magnus")
        cls.b = Player.objects.create(name="Nakamura, Hikaru")
        cls.c = Player.objects.create(name="Outro, Alguém")

    def play(self, white, black, outcome, day, **extra):
        data = {"time_category": BLITZ, "date": day, "outcome": outcome}
        data.update(extra)
        return Match.objects.create(player_white=white, player_black=black, **data)

    def test_results_are_counted_from_a_perspective_in_both_colours(self):
        self.play(self.a, self.b, Outcome.WHITE_WINS, date(2026, 1, 1))  # A wins
        self.play(self.b, self.a, Outcome.BLACK_WINS, date(2026, 1, 2))  # A wins
        self.play(self.b, self.a, Outcome.WHITE_WINS, date(2026, 1, 3))  # A loses
        self.play(self.a, self.b, Outcome.DRAW, date(2026, 1, 4))

        total = head_to_head(self.a, self.b).overall
        self.assertEqual((total.wins, total.draws, total.losses), (2, 1, 1))
        flipped = head_to_head(self.b, self.a).overall
        self.assertEqual((flipped.wins, flipped.draws, flipped.losses), (1, 1, 2))

    def test_other_games_and_unfinished_ones_do_not_count(self):
        self.play(self.a, self.c, Outcome.WHITE_WINS, date(2026, 1, 1))
        self.play(self.a, self.b, Outcome.ONGOING, date(2026, 1, 2))
        self.assertEqual(head_to_head(self.a, self.b).overall.games, 0)

    def test_tallies_by_mode(self):
        self.play(self.a, self.b, Outcome.WHITE_WINS, date(2026, 1, 1), online=False)
        self.play(self.a, self.b, Outcome.DRAW, date(2026, 1, 2), online=True)
        self.play(self.a, self.b, Outcome.DRAW, date(2026, 1, 3), online=True)
        result = head_to_head(self.a, self.b)
        self.assertEqual((result.otb.games, result.online.games, result.overall.games), (1, 2, 3))
        self.assertIs(result.for_mode("presencial"), result.otb)
        self.assertIs(result.for_mode("online"), result.online)
        self.assertIs(result.for_mode("todos"), result.overall)

    def test_recent_meetings_are_newest_first_limited_and_link_to_lichess(self):
        for day in range(1, 8):
            self.play(
                self.a,
                self.b,
                Outcome.WHITE_WINS,
                date(2026, 2, day),
                source=Source.LICHESS,
                external_id=f"g{day}",
            )
        recent = head_to_head(self.a, self.b).recent
        self.assertEqual(len(recent), 5)
        self.assertEqual(recent[0].date, date(2026, 2, 7))
        self.assertEqual(recent[0].url, "https://lichess.org/g7")
        self.assertEqual(recent[0].result, "W")
        self.assertEqual(recent[0].category_label, "Blitz")


class InsightsTests(TestCase):
    def setUp(self):
        self.a = Player(name="Carlsen, Magnus")
        self.b = Player(name="Nakamura, Hikaru")

    def insights(self, a_pool, b_pool, h2h=None):
        from .versus import HeadToHead

        otb, online = build_rows(a_pool, b_pool)
        return build_insights(self.a, self.b, otb + online, h2h or HeadToHead())

    def test_who_leads_more_ratings(self):
        a_pool = {
            (Source.FIDE, CLASSICAL): 2830,
            (Source.FIDE, RAPID): 2800,
            (Source.FIDE, BLITZ): 2700,
        }
        b_pool = {
            (Source.FIDE, CLASSICAL): 2800,
            (Source.FIDE, RAPID): 2790,
            (Source.FIDE, BLITZ): 2750,
        }
        first = self.insights(a_pool, b_pool)[0]
        self.assertEqual(first.figure, "2 de 3")
        self.assertIn("Magnus lidera", first.text)

    def test_a_tie_in_leads(self):
        a_pool = {(Source.FIDE, CLASSICAL): 2830, (Source.FIDE, BLITZ): 2700}
        b_pool = {(Source.FIDE, CLASSICAL): 2800, (Source.FIDE, BLITZ): 2750}
        self.assertEqual(self.insights(a_pool, b_pool)[0].figure, "1 = 1")

    def test_the_widest_gap_names_its_owner_and_rating(self):
        a_pool = {(Source.FIDE, CLASSICAL): 2830, (Source.FIDE, BLITZ): 2700}
        b_pool = {(Source.FIDE, CLASSICAL): 2800, (Source.FIDE, BLITZ): 2760}
        second = self.insights(a_pool, b_pool)[1]
        self.assertEqual(second.figure, "60")
        self.assertIn("Hikaru no Blitz FIDE", second.text)

    def test_nothing_comparable(self):
        first, second, third = self.insights({(Source.FIDE, CLASSICAL): 2800}, {})
        self.assertEqual((first.figure, second.figure, third.figure), ("–", "–", "0"))
        self.assertIn("partidas entre os dois", third.text)

    def test_head_to_head_record_and_wording(self):
        from .services import Tally
        from .versus import HeadToHead

        one = Tally(games=1, wins=1)
        many = Tally(games=7, wins=4, draws=2, losses=1)
        single = self.insights({}, {}, HeadToHead(overall=one))[2]
        plural = self.insights({}, {}, HeadToHead(overall=many))[2]
        self.assertEqual(single.figure, "1-0-0")
        self.assertIn("1 partida registada.", single.text)
        self.assertEqual(plural.figure, "4-2-1")
        self.assertIn("Magnus, empates e Hikaru, em 7 partidas registadas.", plural.text)


class VersusPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Player.objects.create(
            name="Carlsen, Magnus", title="GM", federation="NOR", fide_id=1503014, is_active=True
        )
        cls.b = Player.objects.create(
            name="Nakamura, Hikaru", title="GM", federation="USA", fide_id=2016192, is_active=True
        )
        rate(cls.a, Source.FIDE, CLASSICAL, 2830)
        rate(cls.b, Source.FIDE, CLASSICAL, 2800)
        rate(cls.a, Source.LICHESS, BLITZ, 3200)
        Match.objects.create(
            player_white=cls.a,
            player_black=cls.b,
            outcome=Outcome.WHITE_WINS,
            time_category=BLITZ,
            date=date(2026, 5, 1),
            online=True,
        )

    def url(self, **params):
        return reverse("versus", args=[self.a.pk, self.b.pk]) + (
            "?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else ""
        )

    def test_the_form_page(self):
        response = self.client.get(reverse("versus_form"))
        self.assertContains(response, "Quem enfrenta quem?")

    def test_the_form_redirects_to_the_comparison(self):
        response = self.client.get(reverse("versus_form"), {"a": "carlsen", "b": "nakamura"})
        self.assertRedirects(response, self.url())

    def test_the_form_explains_what_it_could_not_find(self):
        response = self.client.get(reverse("versus_form"), {"a": "carlsen", "b": "zzz"})
        self.assertContains(response, "Não encontrei nenhum jogador para «zzz».")
        self.assertContains(response, 'value="carlsen"')

    def test_the_form_refuses_the_same_player_twice(self):
        response = self.client.get(reverse("versus_form"), {"a": "carlsen", "b": "1503014"})
        self.assertContains(response, "Escolhe dois jogadores diferentes.")

    def test_the_comparison_page(self):
        response = self.client.get(self.url())
        self.assertContains(response, "Magnus")
        self.assertContains(response, "Carlsen")
        self.assertContains(response, "Hikaru")
        self.assertContains(response, "Nakamura")
        self.assertContains(response, "NOR")
        self.assertContains(response, 'style="--t:2830"')
        self.assertContains(response, 'style="--t:2800"')
        self.assertContains(response, "Presencial · rating FIDE")
        self.assertContains(response, "Só rápido e blitz")
        self.assertContains(response, "Lichess")
        self.assertContains(response, "O que os números dizem")
        self.assertContains(response, 'class="lead"')  # the leading bar is marked

    def test_mode_filters(self):
        presencial = self.client.get(self.url(modo="presencial"))
        online = self.client.get(self.url(modo="online"))
        self.assertContains(presencial, "Presencial · rating FIDE")
        self.assertNotContains(presencial, "Só rápido e blitz")
        self.assertNotContains(online, "Presencial · rating FIDE")
        self.assertContains(online, "Só rápido e blitz")

    def test_an_unknown_mode_falls_back_to_everything(self):
        response = self.client.get(self.url(modo="<script>"))
        self.assertEqual(response.context["mode"], "todos")

    def test_missing_or_equal_players_are_a_404(self):
        self.assertEqual(
            self.client.get(reverse("versus", args=[self.a.pk, 99999])).status_code, 404
        )
        self.assertEqual(
            self.client.get(reverse("versus", args=[self.a.pk, self.a.pk])).status_code, 404
        )

    def test_empty_online_section_says_what_to_do(self):
        lonely = Player.objects.create(name="Sem, Dados")
        response = self.client.get(reverse("versus", args=[lonely.pk, self.b.pk]))
        self.assertContains(response, "Ainda não há ratings online")

    def test_names_cannot_inject_html(self):
        evil = Player.objects.create(name="<script>alert(1)</script>, <b>x</b>")
        response = self.client.get(reverse("versus", args=[evil.pk, self.b.pk]))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertNotContains(response, "<b>x</b>")

    def test_the_navigation_links_to_the_comparison(self):
        self.assertContains(self.client.get(reverse("home")), reverse("versus_form"))

    def test_the_number_of_queries_does_not_grow_with_the_games(self):
        def count():
            with CaptureQueriesContext(connection) as queries:
                self.client.get(self.url())
            return len(queries)

        before = count()
        for day in range(1, 20):
            Match.objects.create(
                player_white=self.b,
                player_black=self.a,
                outcome=Outcome.DRAW,
                time_category=RAPID,
                date=date(2026, 6, day),
            )
        self.assertEqual(count(), before)
        self.assertLessEqual(before, 10)
