from datetime import date
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from core.choices import Source
from player.models import Platform, Player, PlayerAccount
from tournaments.models import Format, Tournament, TournamentResult, TournamentStatus

from .chesscom import (
    ChesscomClient,
    ChesscomError,
    ChesscomNotFound,
    ChesscomRateLimited,
    ChesscomStanding,
    parse_event,
    parse_standings,
)
from .chesscom_tournaments import sync_standings, upsert_event
from .testing import FakeResponse, FakeSession
from .testing_tournaments import (
    SLUG,
    START,
    event_data,
    group_data,
    last_round,
    round_urls,
)


class TournamentClientTests(SimpleTestCase):
    def test_details_address_and_slug_check(self):
        session = FakeSession(FakeResponse(payload={"ok": 1}))
        client = ChesscomClient(session=session)
        self.assertEqual(client.get_tournament(SLUG), {"ok": 1})
        self.assertEqual(session.calls[0]["url"], f"https://api.chess.com/pub/tournament/{SLUG}")
        for bad in ("../x", "Titled Tuesday", "a", "x/y"):
            with self.subTest(slug=bad), self.assertRaises(ChesscomError):
                client.get_tournament(bad)

    def test_pages_must_be_tournament_addresses(self):
        client = ChesscomClient(session=FakeSession(FakeResponse(payload={"groups": []})))
        self.assertEqual(client.get_tournament_page(round_urls()[-1]), {"groups": []})
        for bad in (
            "https://evil.example.com/pub/tournament/x/1",
            "https://api.chess.com/pub/player/x",
        ):
            with self.subTest(url=bad), self.assertRaises(ChesscomError):
                client.get_tournament_page(bad)


class ParseTests(SimpleTestCase):
    def test_a_finished_event(self):
        event = parse_event(event_data(winner="firouzja2003"))
        self.assertEqual(event.status, "finished")
        self.assertEqual((event.start, event.end), (date(2026, 11, 3), date(2026, 11, 3)))
        self.assertEqual((event.rounds, len(event.round_urls)), (11, 11))
        self.assertEqual(event.winner, "firouzja2003")

    def test_an_event_without_times_or_winner(self):
        event = parse_event(event_data(start=None, finish=None, status="in_progress"))
        self.assertEqual((event.start, event.end, event.winner), (None, None, ""))
        self.assertEqual(event.status, "in_progress")

    def test_rounds_fall_back_to_the_listed_ones(self):
        data = event_data()
        del data["settings"]["total_rounds"]
        self.assertEqual(parse_event(data).rounds, 11)

    def test_standings_keep_decimal_points_and_skip_incomplete_entries(self):
        group = group_data(("firouzja2003", 10), ("hikaru", 9.5))
        group["players"] += [{"username": "nopoints"}, {"points": 3}]
        standings = parse_standings(group)
        self.assertEqual(
            [(s.username, s.points, s.is_winner) for s in standings],
            [("firouzja2003", Decimal("10"), True), ("hikaru", Decimal("9.5"), False)],
        )
        self.assertEqual(parse_standings({}), [])


class UpsertEventTests(TestCase):
    def test_creates_a_finished_swiss_tournament(self):
        tournament = upsert_event(SLUG, parse_event(event_data()))
        self.assertEqual((tournament.source, tournament.external_id), (Source.CHESSCOM, SLUG))
        self.assertEqual(tournament.name, "Titled Tuesday Blitz November 03 2026")
        self.assertEqual(
            (tournament.format, tournament.status), (Format.SWISS, TournamentStatus.FINISHED)
        )
        self.assertEqual(
            (tournament.start_date, tournament.end_date, tournament.rounds),
            (date(2026, 11, 3), date(2026, 11, 3), 11),
        )

    def test_refreshes_an_event_created_from_games(self):
        Tournament.objects.create(
            source=Source.CHESSCOM,
            external_id=SLUG,
            name="x",
            format=Format.SWISS,
            start_date=date(2026, 11, 4),
            end_date=date(2026, 11, 5),
            status=TournamentStatus.ONGOING,
        )
        tournament = upsert_event(SLUG, parse_event(event_data()))
        self.assertEqual(Tournament.objects.count(), 1)
        self.assertEqual(
            (tournament.start_date, tournament.end_date), (date(2026, 11, 3), date(2026, 11, 3))
        )
        self.assertEqual(tournament.status, TournamentStatus.FINISHED)

    def test_unfinished_events_are_ongoing(self):
        tournament = upsert_event(SLUG, parse_event(event_data(status="in_progress", finish=None)))
        self.assertEqual(
            (tournament.status, tournament.end_date), (TournamentStatus.ONGOING, date(2026, 11, 3))
        )


class SyncStandingsTests(TestCase):
    def setUp(self):
        self.tournament = upsert_event(SLUG, parse_event(event_data()))

    def standings(self, *pairs):
        return [
            ChesscomStanding(name, Decimal(str(points)), i == 0)
            for i, (name, points) in enumerate(pairs)
        ]

    def test_stores_points_and_placements_with_ties_sharing_a_place(self):
        count = sync_standings(
            self.tournament, self.standings(("A", 10), ("B", 9.5), ("C", 9.5), ("D", 8))
        )
        self.assertEqual(count, 4)
        rows = {
            r.player.name: (r.points, r.placement, r.is_winner)
            for r in TournamentResult.objects.select_related("player")
        }
        self.assertEqual(
            rows,
            {
                "A": (Decimal("10.0"), 1, True),
                "B": (Decimal("9.5"), 2, False),
                "C": (Decimal("9.5"), 2, False),
                "D": (Decimal("8.0"), 4, False),
            },
        )

    def test_known_accounts_are_reused_ignoring_case_and_the_rest_become_minimal_players(self):
        hikaru = Player.objects.create(name="Nakamura, Hikaru")
        PlayerAccount.objects.create(player=hikaru, platform=Platform.CHESSCOM, username="Hikaru")
        sync_standings(self.tournament, self.standings(("hikaru", 9.5), ("Newcomer", 5)))

        self.assertEqual(TournamentResult.objects.get(player=hikaru).points, Decimal("9.5"))
        newcomer = PlayerAccount.objects.get(username="Newcomer")
        self.assertEqual((newcomer.platform, newcomer.player.name), (Platform.CHESSCOM, "Newcomer"))
        self.assertEqual(Player.objects.count(), 2)

    def test_repeating_updates_instead_of_duplicating(self):
        sync_standings(self.tournament, self.standings(("A", 10), ("B", 9)))
        sync_standings(self.tournament, self.standings(("A", 10), ("B", 9.5)))
        self.assertEqual(TournamentResult.objects.count(), 2)
        self.assertEqual(TournamentResult.objects.get(player__name="B").points, Decimal("9.5"))
        self.assertEqual(Player.objects.count(), 2)

    def test_two_accounts_of_one_person_keep_the_better_score(self):
        ana = Player.objects.create(name="Ana")
        for username in ("AnaMain", "AnaAlt"):
            PlayerAccount.objects.create(player=ana, platform=Platform.CHESSCOM, username=username)
        count = sync_standings(self.tournament, self.standings(("AnaAlt", 4), ("AnaMain", 7)))
        self.assertEqual(count, 1)
        self.assertEqual(TournamentResult.objects.get(player=ana).points, Decimal("7.0"))

    def test_other_platforms_accounts_are_not_mixed_up(self):
        lichess = Player.objects.create(name="Someone on Lichess")
        PlayerAccount.objects.create(player=lichess, platform=Platform.LICHESS, username="Zed")
        sync_standings(self.tournament, self.standings(("Zed", 6)))
        self.assertFalse(TournamentResult.objects.filter(player=lichess).exists())


class FakeTournaments:
    """Stands in for ChesscomClient. events: {slug: details}; pages: {url: page or exception}."""

    def __init__(self, events=None, pages=None):
        self.events, self.pages, self.requested = events or {}, pages or {}, []

    def get_tournament(self, slug):
        self.requested.append(slug)
        if slug not in self.events:
            raise ChesscomNotFound(slug)
        value = self.events[slug]
        if isinstance(value, Exception):
            raise value
        return value

    def get_tournament_page(self, url):
        value = self.pages[url]
        if isinstance(value, Exception):
            raise value
        return value


def finished_event(slug, winner="firouzja2003", day=START):
    return {
        "events": {slug: event_data(slug, winner=winner, start=day, finish=day + 8000)},
        "pages": {
            last_round(slug)["groups"][0]: group_data(
                (winner, 10), ("hikaru", 9.5), ("magnuscarlsen", 8)
            ),
            round_urls(slug)[-1]: last_round(slug),
        },
    }


class SyncTitledTuesdayCommandTests(TestCase):
    target = "player.management.commands.sync_titled_tuesday"

    def run_command(self, fake, *args):
        out = StringIO()
        with (
            mock.patch(f"{self.target}.ChesscomClient", return_value=fake),
            mock.patch(f"{self.target}.time.sleep"),
        ):
            call_command("sync_titled_tuesday", *args, stdout=out)
        return out.getvalue()

    def fake_for(self, *slugs):
        events, pages = {}, {}
        for index, slug in enumerate(slugs):
            parts = finished_event(slug, day=START + index * 7 * 86400)
            events.update(parts["events"])
            pages.update(parts["pages"])
        return FakeTournaments(events, pages)

    def test_reads_an_event_by_name_and_stores_its_standings(self):
        output = self.run_command(self.fake_for(SLUG), "--slug", SLUG)

        self.assertIn("3 players, winner firouzja2003", output)
        self.assertIn("Done: 1 event(s) stored, 0 skipped.", output)
        tournament = Tournament.objects.get(external_id=SLUG)
        self.assertEqual(tournament.results.count(), 3)
        self.assertEqual(tournament.results.get(player__name="hikaru").placement, 2)

    def test_recent_reads_the_newest_events_already_in_the_database(self):
        slugs = [f"titled-tuesday-blitz-event-{n}-{3000 + n}" for n in range(1, 4)]
        for n, slug in enumerate(slugs):
            Tournament.objects.create(
                source=Source.CHESSCOM,
                external_id=slug,
                name=slug,
                format=Format.SWISS,
                start_date=date(2026, 10, 1 + 7 * n),
            )
        fake = self.fake_for(*slugs)
        self.run_command(fake, "--recent", "2")
        self.assertEqual(fake.requested, [slugs[2], slugs[1]])  # newest first

    def test_without_events_or_a_name_it_explains_what_to_do(self):
        with self.assertRaisesMessage(CommandError, "sync_chesscom"):
            self.run_command(FakeTournaments())

    def test_stored_events_are_skipped_unless_forced(self):
        fake = self.fake_for(SLUG)
        self.run_command(fake, "--slug", SLUG)
        output = self.run_command(fake, "--slug", SLUG)
        self.assertIn("already stored", output)
        self.assertIn("0 event(s) stored, 1 skipped", output)
        forced = self.run_command(fake, "--slug", SLUG, "--force")
        self.assertIn("1 event(s) stored", forced)
        self.assertEqual(TournamentResult.objects.count(), 3)

    def test_an_event_still_running_is_recorded_but_not_read(self):
        fake = FakeTournaments({SLUG: event_data(status="in_progress", finish=None)})
        output = self.run_command(fake, "--slug", SLUG)
        self.assertIn("not finished yet", output)
        self.assertEqual(Tournament.objects.get().status, TournamentStatus.ONGOING)
        self.assertEqual(TournamentResult.objects.count(), 0)

    def test_an_event_that_fails_is_skipped_and_the_others_are_kept(self):
        good = "titled-tuesday-blitz-good-event-31"
        bad = "titled-tuesday-blitz-bad-event-32"
        fake = self.fake_for(good)
        fake.events[bad] = ChesscomError("Chess.com answered 500")
        output = self.run_command(fake, "--slug", bad, "--slug", good)
        self.assertIn(f"skipped {bad}", output)
        self.assertIn("1 event(s) stored, 1 skipped", output)

    def test_hitting_the_rate_limit_stops_the_command(self):
        fake = FakeTournaments({SLUG: ChesscomRateLimited("slow down")})
        with self.assertRaisesMessage(CommandError, "slow down"):
            self.run_command(fake, "--slug", SLUG)

    def test_an_event_without_standings_is_reported(self):
        parts = finished_event(SLUG)
        parts["pages"][last_round(SLUG)["groups"][0]] = group_data()
        output = self.run_command(FakeTournaments(**parts), "--slug", SLUG)
        self.assertIn("no standings found", output)

    def test_invalid_arguments(self):
        for slug in ("../x", "bullet-brawl-2025-123456"):
            with (
                self.subTest(slug=slug),
                self.assertRaisesMessage(CommandError, "not a Titled Tuesday event"),
            ):
                self.run_command(FakeTournaments(), "--slug", slug)
        with self.assertRaisesMessage(CommandError, "at least 1"):
            self.run_command(FakeTournaments(), "--recent", "0")
