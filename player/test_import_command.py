import tempfile
from datetime import date
from io import StringIO
from pathlib import Path
from unittest import mock

import requests
from django.core.management import CommandError, call_command
from django.test import TestCase

from core.choices import Source, TimeCategory
from history_rating.models import HistoryRating

from .models import Player
from .testing import player_xml, write_list


class ImportFidePlayersTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def run_import(self, *players, as_zip=True, **options):
        path = write_list(self.directory, *players, as_zip=as_zip)
        out = StringIO()
        options.setdefault("period", "2026-10")
        call_command("import_fide_players", file=path, stdout=out, **options)
        return out.getvalue()

    def sample(self):
        return [
            player_xml(
                5000001,
                name="Silva, Ana",
                title="IM",
                w_title="WGM",
                rating="2400",
                rapid="2350",
                blitz="2300",
                birthday="1995",
            ),
            player_xml(5000002, name="Costa, Rui", rating="1900", birthday="2001"),
            player_xml(5000003, name="Unrated, Una"),
        ]

    def test_creates_players_and_ratings_for_the_period(self):
        output = self.run_import(*self.sample())

        ana = Player.objects.get(fide_id=5000001)
        self.assertEqual(
            (ana.name, ana.federation, ana.birth_year, ana.title, ana.women_title),
            ("Silva, Ana", "ANG", 1995, "IM", "WGM"),
        )
        self.assertEqual(Player.objects.count(), 3)
        ratings = HistoryRating.objects.filter(player=ana)
        self.assertEqual(ratings.count(), 3)
        classical = ratings.get(time_category=TimeCategory.CLASSICAL)
        self.assertEqual(
            (classical.source, classical.rating_date, classical.rating),
            (Source.FIDE, date(2026, 10, 1), 2400),
        )
        self.assertEqual(HistoryRating.objects.count(), 4)  # Ana 3 + Rui 1, Una has none
        self.assertIn("3 players (3 new), 4 ratings for 2026-10", output)

    def test_works_with_a_plain_xml_file(self):
        self.run_import(*self.sample(), as_zip=False)
        self.assertEqual(Player.objects.count(), 3)

    def test_running_twice_changes_nothing(self):
        self.run_import(*self.sample())
        output = self.run_import(*self.sample())

        self.assertEqual(Player.objects.count(), 3)
        self.assertEqual(HistoryRating.objects.count(), 4)
        self.assertIn("(0 new)", output)

    def test_a_newer_list_updates_existing_rows(self):
        self.run_import(*self.sample())
        self.run_import(
            player_xml(5000001, name="Silva, Ana", title="GM", rating="2500"),
            period="2026-10",
        )

        ana = Player.objects.get(fide_id=5000001)
        self.assertEqual((ana.title, ana.women_title), ("GM", ""))
        classical = HistoryRating.objects.get(player=ana, time_category=TimeCategory.CLASSICAL)
        self.assertEqual(classical.rating, 2500)
        self.assertEqual(HistoryRating.objects.filter(player=ana).count(), 3)

    def test_each_period_keeps_its_own_history(self):
        self.run_import(player_xml(5000001, rating="2400"), period="2026-09")
        self.run_import(player_xml(5000001, rating="2420"), period="2026-10")

        ratings = HistoryRating.objects.order_by("rating_date").values_list("rating_date", "rating")
        self.assertEqual(list(ratings), [(date(2026, 9, 1), 2400), (date(2026, 10, 1), 2420)])

    def test_players_added_by_hand_are_left_alone(self):
        manual = Player.objects.create(name="Manual Player", federation="ANG")
        self.run_import(*self.sample())

        manual.refresh_from_db()
        self.assertEqual(manual.name, "Manual Player")
        self.assertIsNone(manual.fide_id)

    def test_repeated_id_in_the_file_keeps_the_last_record(self):
        self.run_import(
            player_xml(5000001, name="Primeiro", rating="2000"),
            player_xml(5000001, name="Segundo", rating="2100"),
        )
        self.assertEqual(Player.objects.get(fide_id=5000001).name, "Segundo")
        self.assertEqual(HistoryRating.objects.get().rating, 2100)

    def test_min_rating_filters_players(self):
        output = self.run_import(*self.sample(), min_rating=2000)
        self.assertEqual(list(Player.objects.values_list("fide_id", flat=True)), [5000001])
        self.assertIn("1 players", output)
        self.assertIn("3 players read", output)

    def test_limit_stops_early(self):
        self.run_import(*self.sample(), limit=2)
        self.assertEqual(Player.objects.count(), 2)

    def test_invalid_period_is_a_clear_error(self):
        with self.assertRaisesMessage(CommandError, "--period must look like 2026-10"):
            self.run_import(*self.sample(), period="outubro")

    def test_missing_file_is_a_clear_error(self):
        with self.assertRaisesMessage(CommandError, "File not found"):
            call_command("import_fide_players", file=self.directory / "nope.zip", stdout=StringIO())

    def test_unreadable_file_is_a_clear_error(self):
        broken = self.directory / "broken.xml"
        broken.write_text("<playerslist><player>", encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "Could not read"):
            call_command("import_fide_players", file=broken, stdout=StringIO())

    def test_without_a_file_it_downloads_the_current_list(self):
        path = write_list(self.directory, *self.sample())
        with mock.patch(
            "player.management.commands.import_fide_players.download_list", return_value=path
        ) as download:
            call_command("import_fide_players", period="2026-10", stdout=StringIO())

        download.assert_called_once()
        self.assertEqual(Player.objects.count(), 3)

    def test_failed_download_suggests_the_manual_route(self):
        with mock.patch(
            "player.management.commands.import_fide_players.download_list",
            side_effect=requests.ConnectionError("no network"),
        ):
            with self.assertRaisesMessage(CommandError, "--file"):
                call_command("import_fide_players", stdout=StringIO())
