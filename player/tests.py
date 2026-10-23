from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Platform, Player, PlayerAccount


def make_player(**overrides):
    data = {"name": "Magnus Carlsen", "federation": "NOR", "birth_year": 1990}
    data.update(overrides)
    return Player.objects.create(**data)


class PlayerTests(TestCase):
    def test_defaults_and_str(self):
        player = make_player()
        self.assertEqual(player.title, "")
        self.assertEqual(player.women_title, "")
        self.assertEqual(str(player), "Magnus Carlsen")

    def test_birth_year_is_optional(self):
        make_player(birth_year=None).full_clean()

    def test_implausible_birth_year_is_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            make_player(birth_year=1850).full_clean()
        self.assertIn("birth_year", caught.exception.message_dict)

    def test_federation_must_be_a_three_letter_code(self):
        player = Player(name="Magnus Carlsen", federation="Norway")
        with self.assertRaises(ValidationError) as caught:
            player.full_clean()
        self.assertIn("federation", caught.exception.message_dict)

    def test_can_hold_both_open_and_women_titles(self):
        player = make_player(title="GM", women_title="WGM")
        player.full_clean()

    def test_fide_id_must_be_unique(self):
        make_player(fide_id=1503014)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_player(name="Outro", fide_id=1503014)

    def test_players_without_fide_id_can_coexist(self):
        make_player(name="Sem FIDE 1")
        make_player(name="Sem FIDE 2")
        self.assertEqual(Player.objects.filter(fide_id__isnull=True).count(), 2)


class PlayerAccountTests(TestCase):
    def test_str_shows_username_and_platform(self):
        account = PlayerAccount.objects.create(
            player=make_player(), platform=Platform.LICHESS, username="TestUser"
        )
        self.assertEqual(str(account), "TestUser (Lichess)")

    def test_player_can_have_several_accounts(self):
        player = make_player()
        PlayerAccount.objects.create(player=player, platform=Platform.LICHESS, username="a1")
        PlayerAccount.objects.create(player=player, platform=Platform.CHESSCOM, username="a2")
        self.assertEqual(player.accounts.count(), 2)

    def test_username_is_unique_per_platform_ignoring_case(self):
        PlayerAccount.objects.create(
            player=make_player(), platform=Platform.LICHESS, username="TestUser"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlayerAccount.objects.create(
                player=make_player(name="Outro"), platform=Platform.LICHESS, username="testuser"
            )

    def test_same_username_is_allowed_on_different_platforms(self):
        PlayerAccount.objects.create(
            player=make_player(), platform=Platform.LICHESS, username="TestUser"
        )
        PlayerAccount.objects.create(
            player=make_player(name="Outro"), platform=Platform.CHESSCOM, username="TestUser"
        )
        self.assertEqual(PlayerAccount.objects.count(), 2)
