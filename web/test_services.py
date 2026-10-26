from datetime import date

from django.test import TestCase

from core.choices import Outcome, Source, TimeCategory
from history_rating.models import HistoryRating
from matches.models import Match
from player.models import Player

from .services import (
    latest_ratings,
    pick_series,
    rating_series,
    recent_games,
    result_for,
    search_players,
    summarize,
    top_rated,
)


def rate(player, source, category, day, rating):
    return HistoryRating.objects.create(
        player=player, source=source, time_category=category, rating_date=day, rating=rating
    )


class ResultForTests(TestCase):
    def test_result_from_each_players_point_of_view(self):
        cases = [
            (Outcome.WHITE_WINS, True, "W"),
            (Outcome.WHITE_WINS, False, "L"),
            (Outcome.BLACK_WINS, True, "L"),
            (Outcome.BLACK_WINS, False, "W"),
            (Outcome.DRAW, True, "D"),
            (Outcome.DRAW, False, "D"),
            (Outcome.ONGOING, True, "*"),
        ]
        for outcome, is_white, expected in cases:
            with self.subTest(outcome=outcome, is_white=is_white):
                self.assertEqual(result_for(outcome, is_white), expected)


class RatingsTests(TestCase):
    def setUp(self):
        self.player = Player.objects.create(name="Silva, Ana")

    def test_latest_rating_per_pool_ordered_fide_first_classical_first(self):
        classical, blitz = TimeCategory.CLASSICAL, TimeCategory.BLITZ
        rate(self.player, Source.LICHESS, blitz, date(2026, 10, 1), 2900)
        rate(self.player, Source.FIDE, blitz, date(2026, 9, 1), 2600)
        rate(self.player, Source.FIDE, classical, date(2026, 8, 1), 2700)
        rate(self.player, Source.FIDE, classical, date(2026, 9, 1), 2710)

        rows = latest_ratings(self.player)

        self.assertEqual(
            [(r.source, r.category, r.rating) for r in rows],
            [
                (Source.FIDE, classical, 2710),
                (Source.FIDE, blitz, 2600),
                (Source.LICHESS, blitz, 2900),
            ],
        )
        self.assertEqual(rows[0].date, date(2026, 9, 1))
        self.assertEqual((rows[0].source_label, rows[0].category_label), ("FIDE", "Clássico"))

    def test_a_player_without_ratings(self):
        self.assertEqual(latest_ratings(self.player), [])

    def test_other_players_ratings_are_not_mixed_in(self):
        other = Player.objects.create(name="Outro")
        rate(other, Source.FIDE, TimeCategory.CLASSICAL, date(2026, 9, 1), 2000)
        self.assertEqual(latest_ratings(self.player), [])

    def test_series_is_one_pool_in_date_order(self):
        rate(self.player, Source.FIDE, TimeCategory.CLASSICAL, date(2026, 9, 1), 2710)
        rate(self.player, Source.FIDE, TimeCategory.CLASSICAL, date(2026, 8, 1), 2700)
        rate(self.player, Source.FIDE, TimeCategory.BLITZ, date(2026, 8, 1), 2600)
        series = rating_series(self.player, Source.FIDE, TimeCategory.CLASSICAL)
        self.assertEqual(series, [(date(2026, 8, 1), 2700), (date(2026, 9, 1), 2710)])

    def test_pick_series_falls_back_to_the_first_available(self):
        rate(self.player, Source.FIDE, TimeCategory.CLASSICAL, date(2026, 9, 1), 2710)
        rate(self.player, Source.LICHESS, TimeCategory.BLITZ, date(2026, 9, 1), 2900)
        rows = latest_ratings(self.player)

        self.assertEqual(pick_series(rows, "lichess", "blitz").rating, 2900)
        self.assertEqual(pick_series(rows, "lichess", "bullet"), rows[0])  # not available
        self.assertEqual(pick_series(rows, None, None), rows[0])
        self.assertEqual(pick_series(rows, "<script>", "x"), rows[0])
        self.assertIsNone(pick_series([], "fide", "classical"))


class GamesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = Player.objects.create(name="Silva, Ana")
        cls.rui = Player.objects.create(name="Costa, Rui")

    def play(self, white, black, outcome, day, **extra):
        data = {"time_category": TimeCategory.BLITZ, "date": day, "outcome": outcome}
        data.update(extra)
        return Match.objects.create(player_white=white, player_black=black, **data)

    def test_summary_counts_results_from_the_players_point_of_view(self):
        self.play(self.ana, self.rui, Outcome.WHITE_WINS, date(2026, 10, 1))  # Ana wins as white
        self.play(self.rui, self.ana, Outcome.WHITE_WINS, date(2026, 10, 2))  # Ana loses as black
        self.play(self.rui, self.ana, Outcome.DRAW, date(2026, 10, 3))  # draw as black
        self.play(self.ana, self.rui, Outcome.BLACK_WINS, date(2026, 10, 4))  # Ana loses as white

        summary = summarize(self.ana)

        self.assertEqual((summary.overall.games, summary.overall.wins), (4, 1))
        self.assertEqual((summary.overall.draws, summary.overall.losses), (1, 2))
        self.assertEqual(summary.overall.score_percent, 38)  # 1.5 points out of 4
        self.assertEqual((summary.as_white.games, summary.as_white.wins), (2, 1))
        self.assertEqual((summary.as_black.games, summary.as_black.draws), (2, 1))
        self.assertEqual(summary.form, ["L", "D", "L", "W"])  # newest first

    def test_unfinished_games_are_not_counted(self):
        self.play(self.ana, self.rui, Outcome.ONGOING, date(2026, 10, 1))
        summary = summarize(self.ana)
        self.assertEqual(summary.overall.games, 0)
        self.assertIsNone(summary.overall.score_percent)
        self.assertEqual((summary.form, summary.openings, summary.by_category), ([], [], []))

    def test_other_players_games_are_not_counted(self):
        carla = Player.objects.create(name="Mendes, Carla")
        self.play(self.rui, carla, Outcome.WHITE_WINS, date(2026, 10, 1))
        self.assertEqual(summarize(self.ana).overall.games, 0)

    def test_form_keeps_only_the_latest_games(self):
        for day in range(1, 13):
            self.play(self.ana, self.rui, Outcome.WHITE_WINS, date(2026, 10, day))
        self.assertEqual(len(summarize(self.ana).form), 10)

    def test_results_by_time_category_follow_the_usual_order(self):
        self.play(self.ana, self.rui, Outcome.DRAW, date(2026, 10, 1), time_category="bullet")
        self.play(self.ana, self.rui, Outcome.DRAW, date(2026, 10, 2), time_category="classical")
        labels = [label for label, _ in summarize(self.ana).by_category]
        self.assertEqual(labels, ["Clássico", "Bullet"])

    def test_most_played_openings(self):
        for day in (1, 2, 3):
            self.play(
                self.ana,
                self.rui,
                Outcome.WHITE_WINS,
                date(2026, 10, day),
                eco="C20",
                opening="King's Pawn",
            )
        self.play(
            self.ana, self.rui, Outcome.DRAW, date(2026, 10, 4), eco="B90", opening="Sicilian"
        )
        self.play(self.ana, self.rui, Outcome.DRAW, date(2026, 10, 5))  # no opening known

        openings = summarize(self.ana).openings

        self.assertEqual(
            [(o.eco, o.name, o.tally.games) for o in openings],
            [("C20", "King's Pawn", 3), ("B90", "Sicilian", 1)],
        )
        self.assertEqual(openings[0].tally.score_percent, 100)

    def test_recent_games_show_the_opponent_colour_and_lichess_link(self):
        self.play(
            self.ana,
            self.rui,
            Outcome.WHITE_WINS,
            date(2026, 10, 1),
            white_elo=2800,
            black_elo=2700,
            source=Source.LICHESS,
            external_id="abc12345",
        )
        self.play(self.rui, self.ana, Outcome.WHITE_WINS, date(2026, 10, 2), white_elo=2710)

        newest, oldest = recent_games(self.ana)

        self.assertEqual((newest.color, newest.result, newest.opponent), ("black", "L", self.rui))
        self.assertEqual((newest.opponent_rating, newest.own_rating, newest.url), (2710, None, ""))
        self.assertEqual((oldest.color, oldest.result), ("white", "W"))
        self.assertEqual((oldest.opponent_rating, oldest.own_rating), (2700, 2800))
        self.assertEqual(oldest.url, "https://lichess.org/abc12345")
        self.assertEqual(oldest.category_label, "Blitz")

    def test_recent_games_are_limited_and_include_unfinished_ones(self):
        for day in range(1, 6):
            self.play(self.ana, self.rui, Outcome.ONGOING, date(2026, 10, day))
        games = recent_games(self.ana, limit=3)
        self.assertEqual(len(games), 3)
        self.assertEqual({g.result for g in games}, {"*"})

    def test_recent_games_do_not_query_the_database_per_row(self):
        for day in range(1, 8):
            self.play(self.ana, self.rui, Outcome.DRAW, date(2026, 10, day))
        with self.assertNumQueries(1):
            games = recent_games(self.ana)
            _ = [(g.opponent.name, g.opponent.display_name) for g in games]


class SearchAndTopTests(TestCase):
    def test_search_needs_every_word_in_any_order(self):
        magnus = Player.objects.create(name="Carlsen, Magnus", fide_id=1503014)
        Player.objects.create(name="Carlsen, Ingvild")
        Player.objects.create(name="Silva, Ana")

        self.assertEqual(
            search_players("carlsen"), [Player.objects.get(name="Carlsen, Ingvild"), magnus]
        )
        self.assertEqual(search_players("magnus carlsen"), [magnus])
        self.assertEqual(search_players("CARLSEN MAGNUS"), [magnus])
        self.assertEqual(search_players("zzz"), [])
        self.assertEqual(search_players("   "), [])

    def test_search_by_fide_id(self):
        magnus = Player.objects.create(name="Carlsen, Magnus", fide_id=1503014)
        self.assertEqual(search_players("1503014"), [magnus])

    def test_search_shows_the_latest_fide_classical_rating(self):
        magnus = Player.objects.create(name="Carlsen, Magnus")
        rate(magnus, Source.FIDE, TimeCategory.CLASSICAL, date(2026, 9, 1), 2830)
        rate(magnus, Source.FIDE, TimeCategory.CLASSICAL, date(2026, 10, 1), 2840)
        rate(magnus, Source.FIDE, TimeCategory.BLITZ, date(2026, 10, 1), 2900)
        self.assertEqual(search_players("carlsen")[0].fide_classical, 2840)

    def test_search_result_count_is_limited(self):
        for i in range(5):
            Player.objects.create(name=f"Player {i}")
        self.assertEqual(len(search_players("player", limit=3)), 3)

    def test_top_rated_uses_the_newest_list_only(self):
        ana = Player.objects.create(name="Silva, Ana")
        rui = Player.objects.create(name="Costa, Rui")
        rate(ana, Source.FIDE, TimeCategory.CLASSICAL, date(2026, 9, 1), 2900)  # old list
        rate(ana, Source.FIDE, TimeCategory.CLASSICAL, date(2026, 10, 1), 2700)
        rate(rui, Source.FIDE, TimeCategory.CLASSICAL, date(2026, 10, 1), 2750)
        rate(rui, Source.FIDE, TimeCategory.BLITZ, date(2026, 10, 1), 3000)  # other pool
        rate(rui, Source.LICHESS, TimeCategory.CLASSICAL, date(2026, 10, 1), 3000)  # other source

        rows, period = top_rated()

        self.assertEqual(period, date(2026, 10, 1))
        self.assertEqual([(r.player, r.rating) for r in rows], [(rui, 2750), (ana, 2700)])

    def test_top_rated_without_data(self):
        self.assertEqual(top_rated(), ([], None))
