from django.test import SimpleTestCase

from .models import Platform, Player, PlayerAccount


class DisplayNameTests(SimpleTestCase):
    def display(self, name):
        return Player(name=name).display_name

    def test_fide_names_are_turned_around(self):
        self.assertEqual(self.display("Carlsen, Magnus"), "Magnus Carlsen")
        self.assertEqual(self.display("Silva,Ana"), "Ana Silva")
        self.assertEqual(self.display("Nguyen, Thi Minh Thu"), "Thi Minh Thu Nguyen")

    def test_other_names_are_left_alone(self):
        self.assertEqual(self.display("Magnus Carlsen"), "Magnus Carlsen")
        self.assertEqual(self.display("ana_silva_gm"), "ana_silva_gm")
        self.assertEqual(self.display("Smith, Jr., John"), "Smith, Jr., John")
        self.assertEqual(self.display("Silva,"), "Silva,")
        self.assertEqual(self.display(""), "")


class ProfileUrlTests(SimpleTestCase):
    def url(self, platform, username="TestUser"):
        return PlayerAccount(platform=platform, username=username).profile_url

    def test_each_platform_has_its_profile_address(self):
        self.assertEqual(self.url(Platform.LICHESS), "https://lichess.org/@/TestUser")
        self.assertEqual(self.url(Platform.CHESSCOM), "https://www.chess.com/member/TestUser")

    def test_unknown_platform_has_no_address(self):
        self.assertEqual(self.url("other"), "")
