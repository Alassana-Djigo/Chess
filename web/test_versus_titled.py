from datetime import date, timedelta
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.choices import Source
from player.models import Player
from tournaments.models import Format, Tournament, TournamentResult

from .versus import titled_summary, titled_tuesday


def event(n, *, slug=None, source=Source.CHESSCOM, rounds=11):
    slug = slug or f"titled-tuesday-blitz-event-{n}-{30000 + n}"
    return Tournament.objects.create(
        source=source,
        external_id=slug,
        name=slug,
        format=Format.SWISS,
        start_date=date(2026, 10, 1) + timedelta(days=7 * n),
        rounds=rounds,
    )


def result(tournament, player, points, place):
    return TournamentResult.objects.create(
        tournament=tournament, player=player, points=Decimal(str(points)), placement=place
    )


class TitledServiceTests(TestCase):
    def setUp(self):
        self.a = Player.objects.create(name="Carlsen, Magnus")
        self.b = Player.objects.create(name="Nakamura, Hikaru")

    def test_newest_events_first_and_limited(self):
        for n in range(7):
            result(event(n), self.a, 8, 5)
        rows = titled_tuesday(self.a, self.b)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0].label, "12/11/2026")  # event 6: the newest
        self.assertEqual(rows[-1].label, "15/10/2026")  # event 2: the fifth newest

    def test_an_event_with_only_one_of_them_leaves_the_other_empty(self):
        result(event(1), self.b, 9.5, 2)
        (row,) = titled_tuesday(self.a, self.b)
        self.assertEqual((row.a_points, row.a_place, row.a_width), (None, None, 0))
        self.assertEqual((row.b_points, row.b_place), (Decimal("9.5"), 2))
        self.assertIsNone(row.leader)

    def test_participants_are_everyone_with_a_result_in_the_event(self):
        tournament = event(1)
        result(tournament, self.a, 8, 3)
        for index in range(4):
            result(tournament, Player.objects.create(name=f"Other {index}"), 5, 9)
        (row,) = titled_tuesday(self.a, self.b)
        self.assertEqual(row.participants, 5)

    def test_leader_and_bar_lengths(self):
        tournament = event(1)
        result(tournament, self.a, 10, 1)
        result(tournament, self.b, 8, 3)
        (row,) = titled_tuesday(self.a, self.b)
        self.assertEqual((row.leader, row.a_width, row.b_width), ("a", 91, 73))

    def test_a_tie_has_no_leader_and_zero_points_have_no_bar(self):
        level = event(1)
        result(level, self.a, 7, 10)
        result(level, self.b, 7, 10)
        empty = event(2)
        result(empty, self.a, 0, 300)
        result(empty, self.b, 3, 200)
        newest, older = titled_tuesday(self.a, self.b)
        self.assertEqual((older.leader, older.a_width, older.b_width), (None, 64, 64))
        self.assertEqual((newest.leader, newest.a_width), ("b", 0))

    def test_other_tournaments_and_other_sources_are_ignored(self):
        result(event(1, slug="bullet-brawl-2025-123456"), self.a, 8, 3)
        result(event(2, source=Source.LICHESS), self.a, 8, 3)
        self.assertEqual(titled_tuesday(self.a, self.b), [])

    def test_summary_counts_only_events_both_played(self):
        for n, (a_points, b_points) in enumerate([(9, 8), (7, 8.5), (6, 6)]):
            tournament = event(n)
            result(tournament, self.a, a_points, 1)
            result(tournament, self.b, b_points, 2)
        result(event(9), self.a, 11, 1)  # only one of them: left out of the summary
        summary = titled_summary(titled_tuesday(self.a, self.b, limit=10))
        self.assertEqual((summary.both, summary.a_ahead, summary.b_ahead), (3, 1, 1))
        self.assertEqual(summary.a_average, Decimal(22) / 3)
        self.assertEqual(summary.b_average, Decimal("22.5") / 3)

    def test_no_summary_when_they_never_met(self):
        result(event(1), self.a, 8, 3)
        self.assertIsNone(titled_summary(titled_tuesday(self.a, self.b)))
        self.assertIsNone(titled_summary([]))


class TitledPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Player.objects.create(name="Carlsen, Magnus")
        cls.b = Player.objects.create(name="Nakamura, Hikaru")

    def page(self, **params):
        url = reverse("versus", args=[self.a.pk, self.b.pk])
        return self.client.get(url, params)

    def play(self):
        tournament = event(1)
        result(tournament, self.a, 8, 12)
        result(tournament, self.b, 9.5, 2)
        result(tournament, Player.objects.create(name="Third"), 10, 1)
        return tournament

    def test_the_section_shows_points_places_and_the_day(self):
        self.play()
        response = self.page()
        self.assertContains(response, "Titled Tuesday")
        self.assertContains(response, "08/10/2026")
        self.assertContains(response, "9.5")
        self.assertContains(response, "2.º de 3")
        self.assertContains(response, "12.º de 3")
        self.assertContains(response, "11 rondas")

    def test_the_summary_sentence(self):
        self.play()
        response = self.page()
        self.assertContains(response, "Nas 1 edição em que os dois jogaram")
        self.assertContains(response, "Magnus ficou à frente 0 vezes e Hikaru 1.")
        self.assertContains(response, "Média de pontos nessas edições: Magnus 8, Hikaru 9.5.")

    def test_only_online_modes_show_it(self):
        self.play()
        self.assertContains(self.page(modo="online"), "Titled Tuesday")
        self.assertContains(self.page(modo="todos"), "Titled Tuesday")
        self.assertNotContains(self.page(modo="presencial"), "Titled Tuesday")

    def test_empty_state(self):
        response = self.page()
        self.assertContains(response, "Ainda não há classificações do Titled Tuesday")
        self.assertNotContains(response, "ficou à frente")

    def test_the_number_of_queries_does_not_grow_with_the_events(self):
        def count():
            with CaptureQueriesContext(connection) as queries:
                self.page()
            return len(queries)

        self.play()
        before = count()
        for n in range(2, 12):
            tournament = event(n)
            result(tournament, self.a, 7, 20)
            result(tournament, self.b, 8, 10)
        self.assertEqual(count(), before)
        self.assertLessEqual(before, 12)
