import tempfile
import zipfile
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree

import requests
from django.test import SimpleTestCase

from core.choices import TimeCategory

from .fide import (
    clean_name,
    download_list,
    iter_players,
    parse_player,
    split_titles,
)
from .testing import player_xml, write_list


class CleanNameTests(SimpleTestCase):
    def test_collapses_spaces_and_fixes_commas(self):
        self.assertEqual(clean_name("  Silva ,   Ana  "), "Silva, Ana")
        self.assertEqual(clean_name("Silva,, Ana"), "Silva, Ana")

    def test_truncates_to_the_database_limit(self):
        self.assertEqual(len(clean_name("x" * 400)), 150)


class SplitTitlesTests(SimpleTestCase):
    def test_classifies_each_value_by_what_it_is(self):
        cases = [
            (("GM", ""), ("GM", "")),
            (("", "WGM"), ("", "WGM")),
            (("WGM", ""), ("", "WGM")),
            (("WGM", "WGM"), ("", "WGM")),
            (("GM", "WGM"), ("GM", "WGM")),
            ((" gm ", ""), ("GM", "")),
            (("IA", "FT"), ("", "")),  # arbiter titles are not player titles
            (("", ""), ("", "")),
        ]
        for (title, women_title), expected in cases:
            with self.subTest(title=title, women_title=women_title):
                self.assertEqual(split_titles(title, women_title), expected)


class ParsePlayerTests(SimpleTestCase):
    def parse(self, **kwargs):
        return parse_player(ElementTree.fromstring(player_xml(**kwargs)))

    def test_complete_record(self):
        player = self.parse(
            fide_id=5000001,
            name="Silva, Ana",
            title="GM",
            w_title="WGM",
            rating="2510",
            rapid="2480",
            blitz="2455",
            birthday="1995",
        )
        self.assertEqual(player.fide_id, 5000001)
        self.assertEqual(player.name, "Silva, Ana")
        self.assertEqual(player.federation, "ANG")
        self.assertEqual(player.birth_year, 1995)
        self.assertEqual((player.title, player.women_title), ("GM", "WGM"))
        self.assertEqual(
            player.ratings,
            {
                TimeCategory.CLASSICAL: 2510,
                TimeCategory.RAPID: 2480,
                TimeCategory.BLITZ: 2455,
            },
        )

    def test_unrated_categories_are_left_out(self):
        player = self.parse(fide_id=1, rating="1800")
        self.assertEqual(player.ratings, {TimeCategory.CLASSICAL: 1800})

    def test_player_with_no_rating_at_all(self):
        self.assertEqual(self.parse(fide_id=1).ratings, {})

    def test_record_without_a_usable_fide_id_is_skipped(self):
        self.assertIsNone(self.parse(fide_id=""))
        self.assertIsNone(self.parse(fide_id="abc"))
        self.assertIsNone(self.parse(fide_id=0))

    def test_invalid_federation_becomes_blank(self):
        self.assertEqual(self.parse(fide_id=1, country="Angola").federation, "")
        self.assertEqual(self.parse(fide_id=1, country="").federation, "")

    def test_implausible_birth_year_becomes_none(self):
        self.assertIsNone(self.parse(fide_id=1, birthday="0").birth_year)
        self.assertIsNone(self.parse(fide_id=1, birthday="1850").birth_year)
        self.assertIsNone(self.parse(fide_id=1, birthday="").birth_year)

    def test_absurd_rating_is_ignored(self):
        self.assertEqual(self.parse(fide_id=1, rating="99999").ratings, {})

    def test_missing_tags_are_tolerated(self):
        element = ElementTree.fromstring("<player><fideid>7</fideid></player>")
        player = parse_player(element)
        self.assertEqual(player.name, "FIDE #7")
        self.assertEqual(player.ratings, {})

    def test_blank_name_gets_a_placeholder(self):
        self.assertEqual(self.parse(fide_id=9, name="").name, "FIDE #9")


class IterPlayersTests(SimpleTestCase):
    def read(self, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            path = write_list(
                directory,
                player_xml(1, name="Um", rating="2000"),
                player_xml("", name="Sem id"),
                player_xml(3, name="Tres", rating="2100"),
                **kwargs,
            )
            return [player.fide_id for player in iter_players(path)]

    def test_reads_players_from_a_zip(self):
        self.assertEqual(self.read(as_zip=True), [1, 3])

    def test_reads_players_from_a_plain_xml(self):
        self.assertEqual(self.read(as_zip=False), [1, 3])

    def test_zip_without_xml_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("readme.txt", "no players here")
            with self.assertRaises(ValueError):
                list(iter_players(path))


class FakeResponse:
    def __init__(self, chunks=(), error=None):
        self.chunks, self.error = chunks, error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.error:
            raise self.error

    def iter_content(self, chunk_size):
        return iter(self.chunks)


class DownloadListTests(SimpleTestCase):
    def test_writes_the_file_and_leaves_no_partial_one(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "data" / "list.zip"
            response = FakeResponse(chunks=[b"abc", b"def"])
            with mock.patch("player.fide.requests.get", return_value=response) as get:
                download_list(destination, url="https://example.com/list.zip")
            self.assertEqual(destination.read_bytes(), b"abcdef")
            self.assertFalse(destination.with_name("list.zip.part").exists())
            self.assertIn("User-Agent", get.call_args.kwargs["headers"])

    def test_http_error_leaves_no_file(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "list.zip"
            response = FakeResponse(error=requests.HTTPError("403"))
            with mock.patch("player.fide.requests.get", return_value=response):
                with self.assertRaises(requests.HTTPError):
                    download_list(destination)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_name("list.zip.part").exists())
