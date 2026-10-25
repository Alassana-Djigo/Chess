from datetime import date

from django.test import TestCase

from core.choices import Outcome, Source, TimeCategory
from history_rating.models import HistoryRating
from matches.models import Match
from player.models import Platform, Player, PlayerAccount

from .lichess import parse_game, parse_profile
from .lichess_sync import LinkError, link_account, sync_games, sync_ratings
from .testing import lichess_game, lichess_user


def make_player(**overrides):
    data = {"name": "Ana Silva", "federation": "ANG"}
    data.update(overrides)
    return Player.objects.create(**data)


class LinkAccountTests(TestCase):
    def link(self, username="Anna", user_kwargs=None, **options):
        profile = parse_profile(lichess_user(username, **(user_kwargs or {})))
        return link_account(profile, **options)

    def test_links_to_the_player_chosen_by_fide_id(self):
        ana = make_player(fide_id=5000001)
        account, how = self.link(fide_id=5000001)
        self.assertEqual(account.player, ana)
        self.assertEqual(
            (account.platform, account.username, account.external_id), ("lichess", "Anna", "anna")
        )
        self.assertEqual(how, "as you asked")

    def test_links_to_the_player_chosen_by_database_id(self):
        ana = make_player()
        account, _ = self.link(player_id=ana.pk)
        self.assertEqual(account.player, ana)

    def test_unknown_fide_id_or_player_id_is_an_error(self):
        with self.assertRaisesMessage(LinkError, "FIDE id 123"):
            self.link(fide_id=123)
        with self.assertRaisesMessage(LinkError, "player with id 999"):
            self.link(player_id=999)

    def test_uses_the_fide_id_published_on_lichess(self):
        ana = make_player(fide_id=5000001)
        account, how = self.link(user_kwargs={"fide_id": 5000001})
        self.assertEqual(account.player, ana)
        self.assertIn("published on Lichess", how)

    def test_an_explicit_choice_beats_the_published_fide_id(self):
        make_player(fide_id=5000001)
        other = make_player(name="Outra", fide_id=5000002)
        account, _ = self.link(user_kwargs={"fide_id": 5000001}, fide_id=5000002)
        self.assertEqual(account.player, other)

    def test_without_any_hint_it_asks_for_one(self):
        with self.assertRaisesMessage(LinkError, "--create"):
            self.link()
        self.assertEqual(PlayerAccount.objects.count(), 0)

    def test_the_error_mentions_a_published_fide_id_that_is_not_imported(self):
        with self.assertRaisesMessage(LinkError, "FIDE id 5000009"):
            self.link(user_kwargs={"fide_id": 5000009})

    def test_create_makes_a_player_from_the_profile(self):
        _, how = self.link(
            user_kwargs={"real_name": "Ana Silva", "fide_id": 5000009, "title": "IM"}, create=True
        )
        player = Player.objects.get()
        self.assertEqual((player.name, player.fide_id, player.title), ("Ana Silva", 5000009, "IM"))
        self.assertEqual(how, "as a new player")

    def test_create_falls_back_to_the_username(self):
        self.link(create=True)
        self.assertEqual(Player.objects.get().name, "Anna")

    def test_linking_again_reuses_the_account_and_refreshes_its_name(self):
        ana = make_player()
        first, _ = self.link(player_id=ana.pk)
        again, how = self.link(username="ANNA")
        self.assertEqual(again.pk, first.pk)
        self.assertEqual(again.username, "ANNA")
        self.assertEqual(PlayerAccount.objects.count(), 1)
        self.assertEqual(how, "was already linked")

    def test_cannot_move_an_account_to_another_player(self):
        ana = make_player()
        other = make_player(name="Outra")
        self.link(player_id=ana.pk)
        with self.assertRaisesMessage(LinkError, "already linked"):
            self.link(player_id=other.pk)


class SyncRatingsTests(TestCase):
    def setUp(self):
        self.player = make_player()
        self.profile = parse_profile(lichess_user("Anna"))
        self.today = date(2026, 10, 25)

    def test_stores_history_and_todays_current_ratings(self):
        history = {(TimeCategory.BLITZ, date(2026, 9, 1)): 2150}
        count = sync_ratings(self.player, self.profile, history, self.today)

        self.assertEqual(count, 3)  # one history point + bullet and blitz today
        rows = {
            (r.time_category, r.rating_date): r.rating
            for r in HistoryRating.objects.filter(source=Source.LICHESS)
        }
        self.assertEqual(
            rows,
            {
                (TimeCategory.BLITZ, date(2026, 9, 1)): 2150,
                (TimeCategory.BULLET, self.today): 2100,
                (TimeCategory.BLITZ, self.today): 2200,
            },
        )

    def test_repeating_changes_nothing_and_updates_what_moved(self):
        sync_ratings(self.player, self.profile, {}, self.today)
        sync_ratings(self.player, self.profile, {}, self.today)
        self.assertEqual(HistoryRating.objects.count(), 2)

        moved = parse_profile(lichess_user("Anna", perfs={"blitz": {"games": 60, "rating": 2250}}))
        sync_ratings(self.player, moved, {}, self.today)
        blitz = HistoryRating.objects.get(time_category=TimeCategory.BLITZ, rating_date=self.today)
        self.assertEqual(blitz.rating, 2250)

    def test_todays_snapshot_wins_over_a_history_point_of_the_same_day(self):
        history = {(TimeCategory.BLITZ, self.today): 2000}
        sync_ratings(self.player, self.profile, history, self.today)
        blitz = HistoryRating.objects.get(time_category=TimeCategory.BLITZ, rating_date=self.today)
        self.assertEqual(blitz.rating, 2200)

    def test_does_not_touch_ratings_from_other_sources(self):
        HistoryRating.objects.create(
            player=self.player,
            source=Source.FIDE,
            time_category=TimeCategory.BLITZ,
            rating_date=self.today,
            rating=2300,
        )
        sync_ratings(self.player, self.profile, {}, self.today)
        fide = HistoryRating.objects.get(source=Source.FIDE)
        self.assertEqual(fide.rating, 2300)


class SyncGamesTests(TestCase):
    def games(self, *raw):
        return [parse_game(r) for r in raw]

    def test_creates_matches_and_minimal_players_for_unknown_accounts(self):
        new, known, skipped = sync_games(self.games(lichess_game()))

        self.assertEqual((new, known, skipped), (1, 0, 0))
        match = Match.objects.get()
        self.assertEqual((match.source, match.external_id), (Source.LICHESS, "game0001"))
        self.assertEqual((match.player_white.name, match.player_black.name), ("Anna", "Bruno"))
        self.assertEqual(match.outcome, Outcome.WHITE_WINS)
        self.assertEqual(match.time_category, TimeCategory.BLITZ)
        self.assertEqual((match.time_base, match.time_increment), (180, 2))
        self.assertEqual((match.white_elo, match.black_elo), (2400, 2350))
        self.assertEqual((match.eco, match.opening), ("C20", "King's Pawn Game"))
        self.assertEqual(match.date, date(2025, 10, 9))
        self.assertTrue(match.online)
        self.assertIn("1. e4 e5", match.pgn)
        self.assertEqual(PlayerAccount.objects.filter(platform=Platform.LICHESS).count(), 2)

    def test_reuses_players_who_already_have_the_account_ignoring_case(self):
        ana = make_player()
        PlayerAccount.objects.create(player=ana, platform=Platform.LICHESS, username="ANNA")
        sync_games(self.games(lichess_game()))

        self.assertEqual(Match.objects.get().player_white, ana)
        self.assertEqual(Player.objects.count(), 2)  # Ana + the new opponent

    def test_an_opponent_is_created_once_across_games(self):
        sync_games(
            self.games(
                lichess_game("g1", white="Anna", black="Bruno"),
                lichess_game("g2", white="Bruno", black="Carla"),
            )
        )
        self.assertEqual(Player.objects.count(), 3)
        self.assertEqual(Match.objects.count(), 2)

    def test_repeating_creates_nothing_and_updates_the_result(self):
        sync_games(self.games(lichess_game(winner=None, status="started")))
        self.assertEqual(Match.objects.get().outcome, Outcome.ONGOING)

        new, known, _ = sync_games(self.games(lichess_game(winner="black", status="resign")))

        self.assertEqual((new, known), (0, 1))
        self.assertEqual(Match.objects.count(), 1)
        self.assertEqual(Match.objects.get().outcome, Outcome.BLACK_WINS)
        self.assertEqual(Player.objects.count(), 2)

    def test_two_accounts_of_the_same_person_are_skipped(self):
        ana = make_player()
        for username in ("Anna", "Anna2"):
            PlayerAccount.objects.create(player=ana, platform=Platform.LICHESS, username=username)

        new, known, skipped = sync_games(self.games(lichess_game(white="Anna", black="Anna2")))

        self.assertEqual((new, known, skipped), (0, 0, 1))
        self.assertEqual(Match.objects.count(), 0)
