from django.test import SimpleTestCase

from .models import Player


class NamePartsTests(SimpleTestCase):
    def parts(self, name):
        return Player(name=name).name_parts

    def test_fide_names_give_given_name_and_surname(self):
        self.assertEqual(self.parts("Carlsen, Magnus"), ("Magnus", "Carlsen"))
        self.assertEqual(self.parts("Nguyen, Thi Minh Thu"), ("Thi Minh Thu", "Nguyen"))

    def test_other_names_are_kept_whole(self):
        self.assertEqual(self.parts("Magnus Carlsen"), ("Magnus Carlsen", ""))
        self.assertEqual(self.parts("ana_silva_gm"), ("ana_silva_gm", ""))
        self.assertEqual(self.parts("Smith, Jr., John"), ("Smith, Jr., John", ""))

    def test_short_name_is_the_first_name_when_known(self):
        self.assertEqual(Player(name="Carlsen, Magnus").short_name, "Magnus")
        self.assertEqual(Player(name="Nguyen, Thi Minh Thu").short_name, "Thi")
        self.assertEqual(Player(name="ana_silva_gm").short_name, "ana_silva_gm")
