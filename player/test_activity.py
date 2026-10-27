import tempfile
from io import StringIO
from pathlib import Path
from xml.etree import ElementTree

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from .fide import is_active_flag, parse_player
from .models import Player
from .testing import player_xml, write_list


class ActiveFlagTests(SimpleTestCase):
    def test_fide_flags(self):
        cases = {"": True, "w": True, "i": False, "wi": False, " WI ": False, " I": False}
        for flag, expected in cases.items():
            with self.subTest(flag=flag):
                self.assertEqual(is_active_flag(flag), expected)

    def test_a_record_carries_its_activity(self):
        def parse(flag):
            return parse_player(ElementTree.fromstring(player_xml(1, flag=flag)))

        self.assertTrue(parse("").is_active)
        self.assertTrue(parse("w").is_active)
        self.assertFalse(parse("i").is_active)
        self.assertFalse(parse("wi").is_active)

    def test_a_record_without_the_flag_tag_counts_as_active(self):
        element = ElementTree.fromstring("<player><fideid>7</fideid></player>")
        self.assertTrue(parse_player(element).is_active)


class ImportActivityTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def run_import(self, *players):
        path = write_list(self.directory, *players)
        call_command("import_fide_players", file=path, period="2026-10", stdout=StringIO())

    def test_activity_is_stored(self):
        self.run_import(
            player_xml(1, name="Activo, A", rating="2500"),
            player_xml(2, name="Inactivo, I", rating="2500", flag="i"),
            player_xml(3, name="Mulher, M", rating="2400", flag="w"),
            player_xml(4, name="Mulher Inactiva, M", rating="2400", flag="wi"),
        )
        found = dict(Player.objects.values_list("fide_id", "is_active"))
        self.assertEqual(found, {1: True, 2: False, 3: True, 4: False})

    def test_a_later_list_updates_the_activity(self):
        self.run_import(player_xml(1, rating="2500"))
        self.run_import(player_xml(1, rating="2500", flag="i"))
        self.assertIs(Player.objects.get(fide_id=1).is_active, False)

    def test_players_not_from_fide_have_unknown_activity(self):
        manual = Player.objects.create(name="Manual")
        self.assertIsNone(manual.is_active)
