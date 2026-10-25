from datetime import UTC, date, datetime

import requests
from django.test import SimpleTestCase

from core.choices import Outcome, TimeCategory

from .lichess import (
    LichessClient,
    LichessError,
    LichessNotFound,
    LichessRateLimited,
    parse_game,
    parse_profile,
    parse_rating_history,
)
from .testing import FakeResponse, FakeSession, lichess_game, lichess_user


def client_for(*responses, **kwargs):
    session = FakeSession(*responses, error=kwargs.pop("error", None))
    sleeps = []
    client = LichessClient(session=session, sleep=sleeps.append, **kwargs)
    return client, session, sleeps


class LichessClientTests(SimpleTestCase):
    def test_get_user_asks_for_the_fide_id(self):
        client, session, _ = client_for(FakeResponse(payload={"id": "anna"}))
        self.assertEqual(client.get_user("Anna"), {"id": "anna"})
        call = session.calls[0]
        self.assertEqual(call["url"], "https://lichess.org/api/user/Anna")
        self.assertEqual(call["params"], {"fideId": "true"})
        self.assertEqual(call["headers"], {"Accept": "application/json"})
        self.assertIn("User-Agent", session.headers)

    def test_username_is_quoted_in_the_path(self):
        client, session, _ = client_for(FakeResponse(payload={}))
        client.get_user("a/b")
        self.assertEqual(session.calls[0]["url"], "https://lichess.org/api/user/a%2Fb")

    def test_token_is_sent_when_given(self):
        _, session, _ = client_for(token="secret")
        self.assertEqual(session.headers["Authorization"], "Bearer secret")

    def test_no_token_means_no_authorization_header(self):
        _, session, _ = client_for()
        self.assertNotIn("Authorization", session.headers)

    def test_unknown_user_raises_not_found(self):
        client, _, _ = client_for(FakeResponse(status_code=404))
        with self.assertRaises(LichessNotFound):
            client.get_user("nobody")

    def test_waits_a_minute_after_429_and_retries(self):
        notes = []
        client, session, sleeps = client_for(
            FakeResponse(status_code=429),
            FakeResponse(payload={"id": "anna"}),
            notify=notes.append,
        )
        self.assertEqual(client.get_user("Anna"), {"id": "anna"})
        self.assertEqual(sleeps, [60])
        self.assertEqual(len(session.calls), 2)
        self.assertIn("waiting 60s", notes[0])

    def test_gives_up_when_429_persists(self):
        client, session, sleeps = client_for(*[FakeResponse(status_code=429)] * 3)
        with self.assertRaises(LichessRateLimited):
            client.get_user("Anna")
        self.assertEqual(sleeps, [60, 60])
        self.assertEqual(len(session.calls), 3)

    def test_server_error_raises(self):
        client, _, _ = client_for(FakeResponse(status_code=500))
        with self.assertRaisesMessage(LichessError, "500"):
            client.get_user("Anna")

    def test_network_error_raises(self):
        client, _, _ = client_for(error=requests.ConnectionError("down"))
        with self.assertRaisesMessage(LichessError, "Could not reach Lichess"):
            client.get_user("Anna")

    def test_unreadable_answer_raises(self):
        client, _, _ = client_for(FakeResponse(payload=None))
        with self.assertRaisesMessage(LichessError, "unreadable"):
            client.get_user("Anna")

    def test_iter_games_reads_ndjson_and_skips_blank_lines(self):
        response = FakeResponse(lines=[{"id": "a"}, b"", {"id": "b"}])
        client, session, _ = client_for(response)
        self.assertEqual([g["id"] for g in client.iter_games("Anna", 5)], ["a", "b"])
        call = session.calls[0]
        self.assertEqual(call["headers"], {"Accept": "application/x-ndjson"})
        self.assertTrue(call["stream"])
        self.assertEqual(call["params"]["max"], 5)
        self.assertEqual(call["params"]["rated"], "true")
        self.assertEqual(call["params"]["perfType"], "bullet,blitz,rapid,classical")
        self.assertEqual(call["params"]["pgnInJson"], "true")
        self.assertTrue(response.closed)

    def test_broken_game_stream_raises(self):
        client, _, _ = client_for(FakeResponse(lines=[{"id": "a"}, b"{not json"]))
        with self.assertRaisesMessage(LichessError, "interrupted"):
            list(client.iter_games("Anna", 5))

    def test_dropped_game_stream_raises(self):
        response = FakeResponse(lines=[{"id": "a"}], stream_error=requests.ConnectionError("cut"))
        client, _, _ = client_for(response)
        with self.assertRaisesMessage(LichessError, "interrupted"):
            list(client.iter_games("Anna", 5))


class ParseProfileTests(SimpleTestCase):
    def test_reads_identity_and_current_ratings(self):
        profile = parse_profile(
            lichess_user("Anna", fide_id=5000001, title="GM", real_name=" Ana Silva ")
        )
        self.assertEqual((profile.id, profile.username), ("anna", "Anna"))
        self.assertEqual(
            (profile.title, profile.real_name, profile.fide_id), ("GM", "Ana Silva", 5000001)
        )
        self.assertFalse(profile.closed)

    def test_provisional_unplayed_and_other_pools_are_left_out(self):
        profile = parse_profile(lichess_user("Anna"))
        self.assertEqual(profile.ratings, {TimeCategory.BULLET: 2100, TimeCategory.BLITZ: 2200})

    def test_optional_fields_may_be_missing(self):
        profile = parse_profile({"id": "anna"})
        self.assertEqual(profile.username, "anna")
        self.assertEqual((profile.title, profile.real_name, profile.fide_id), ("", "", None))
        self.assertEqual(profile.ratings, {})

    def test_titles_that_are_not_fide_titles_are_ignored(self):
        self.assertEqual(parse_profile(lichess_user("Bot", title="BOT")).title, "")
        self.assertEqual(parse_profile(lichess_user("Wnm", title="WNM")).title, "")

    def test_closed_accounts_are_flagged(self):
        self.assertTrue(parse_profile(lichess_user("Anna", disabled=True)).closed)
        self.assertTrue(parse_profile({"id": "anna", "tosViolation": True}).closed)


class ParseRatingHistoryTests(SimpleTestCase):
    def test_maps_pools_and_converts_zero_based_months(self):
        data = [
            {"name": "bullet", "points": [[2026, 5, 25, 1318], [2026, 6, 4, 1143]]},
            {"name": "classical", "points": [[2025, 0, 1, 1500]]},
        ]
        self.assertEqual(
            parse_rating_history(data),
            {
                (TimeCategory.BULLET, date(2026, 6, 25)): 1318,
                (TimeCategory.BULLET, date(2026, 7, 4)): 1143,
                (TimeCategory.CLASSICAL, date(2025, 1, 1)): 1500,
            },
        )

    def test_other_pools_and_invalid_dates_are_skipped(self):
        data = [
            {"name": "ultraBullet", "points": [[2026, 0, 1, 1800]]},
            {"name": "chess960", "points": [[2026, 0, 1, 1700]]},
            {"name": "blitz", "points": [[2026, 1, 31, 1900], [2026, 0, 2, 1950]]},
        ]
        self.assertEqual(parse_rating_history(data), {(TimeCategory.BLITZ, date(2026, 1, 2)): 1950})

    def test_empty_history(self):
        self.assertEqual(parse_rating_history([]), {})
        self.assertEqual(parse_rating_history(None), {})


class ParseGameTests(SimpleTestCase):
    def test_a_normal_game(self):
        game = parse_game(lichess_game())
        self.assertEqual(game.id, "game0001")
        self.assertEqual((game.white.username, game.white.rating), ("Anna", 2400))
        self.assertEqual((game.black.username, game.black.rating), ("Bruno", 2350))
        self.assertEqual(game.outcome, Outcome.WHITE_WINS)
        self.assertEqual(game.time_category, TimeCategory.BLITZ)
        self.assertEqual((game.time_base, game.time_increment), (180, 2))
        self.assertEqual(game.started_at, datetime(2025, 10, 9, 8, 53, 20, tzinfo=UTC))
        self.assertEqual((game.eco, game.opening), ("C20", "King's Pawn Game"))
        self.assertIn("1. e4 e5", game.pgn)

    def test_outcomes(self):
        cases = [
            (dict(winner="white"), Outcome.WHITE_WINS),
            (dict(winner="black", status="resign"), Outcome.BLACK_WINS),
            (dict(winner=None, status="draw"), Outcome.DRAW),
            (dict(winner=None, status="stalemate"), Outcome.DRAW),
            (dict(winner=None, status="outoftime"), Outcome.DRAW),
            (dict(winner=None, status="started"), Outcome.ONGOING),
        ]
        for kwargs, expected in cases:
            with self.subTest(**kwargs):
                self.assertEqual(parse_game(lichess_game(**kwargs)).outcome, expected)

    def test_games_that_never_happened_are_skipped(self):
        for status in ("aborted", "noStart", "unknownFinish"):
            with self.subTest(status=status):
                self.assertIsNone(parse_game(lichess_game(winner=None, status=status)))

    def test_variants_and_unmapped_speeds_are_skipped(self):
        self.assertIsNone(parse_game(lichess_game(variant="chess960")))
        self.assertIsNone(parse_game(lichess_game(speed="ultraBullet")))
        self.assertIsNone(parse_game(lichess_game(speed="correspondence")))

    def test_the_speed_chosen_by_lichess_is_the_category(self):
        for speed, expected in (
            ("bullet", TimeCategory.BULLET),
            ("rapid", TimeCategory.RAPID),
            ("classical", TimeCategory.CLASSICAL),
        ):
            with self.subTest(speed=speed):
                self.assertEqual(parse_game(lichess_game(speed=speed)).time_category, expected)

    def test_games_against_the_computer_or_anonymous_players_are_skipped(self):
        vs_ai = lichess_game()
        vs_ai["players"]["black"] = {"aiLevel": 3}
        anonymous = lichess_game()
        anonymous["players"]["black"] = {"rating": 1500}
        self.assertIsNone(parse_game(vs_ai))
        self.assertIsNone(parse_game(anonymous))

    def test_an_account_playing_itself_is_skipped(self):
        self.assertIsNone(parse_game(lichess_game(white="Anna", black="anna")))

    def test_missing_optional_parts(self):
        data = lichess_game()
        for key in ("opening", "clock", "pgn"):
            del data[key]
        game = parse_game(data)
        self.assertEqual((game.eco, game.opening, game.pgn), ("", "", ""))
        self.assertEqual((game.time_base, game.time_increment), (None, None))

    def test_invalid_eco_is_dropped(self):
        self.assertEqual(parse_game(lichess_game(eco="?")).eco, "")
