from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from player.models import Platform, Player, PlayerAccount

from .chesscom import parse_profile as parse_chesscom_profile
from .chesscom_sync import link_account as link_chesscom
from .identity import names_compatible
from .lichess import parse_profile as parse_lichess_profile
from .lichess_sync import LinkError
from .lichess_sync import link_account as link_lichess
from .test_chesscom_resilience import FakeChesscom
from .test_sync_command import FakeLichess
from .testing import lichess_user
from .testing_chesscom import chesscom_profile


class NamesCompatibleTests(SimpleTestCase):
    def test_same_person_written_differently(self):
        cases = [
            ("Hikaru Nakamura", "Nakamura, Hikaru"),
            ("hikaru nakamura", "NAKAMURA, HIKARU"),
            ("Hikaru", "Nakamura, Hikaru"),
            ("H. Nakamura", "Nakamura, Hikaru"),
            ("José Núñez", "Nunez, Jose"),
            ("Magnus Carlsen", "Magnus Carlsen"),
        ]
        for claimed, player in cases:
            with self.subTest(claimed=claimed, player=player):
                self.assertTrue(names_compatible(claimed, player))

    def test_clearly_different_people(self):
        self.assertFalse(names_compatible("Hikaru Nakamura", "Blohberger, Felix"))
        self.assertFalse(names_compatible("Magnus", "Silva, Ana"))

    def test_no_name_means_nothing_to_compare(self):
        for claimed in ("", "  ", "A"):  # blank, or a lone initial
            with self.subTest(claimed=claimed):
                self.assertTrue(names_compatible(claimed, "Blohberger, Felix"))


class ChesscomGuardTests(TestCase):
    def setUp(self):
        self.felix = Player.objects.create(name="Blohberger, Felix", fide_id=100)
        self.hikaru = Player.objects.create(name="Nakamura, Hikaru", fide_id=200)

    def link(self, player, **kwargs):
        profile = parse_chesscom_profile(chesscom_profile("hikaru", name="Hikaru Nakamura"))
        return link_chesscom(profile, player_id=player.pk, **kwargs)

    def test_a_wrong_player_is_refused_and_nothing_is_created(self):
        with self.assertRaises(LinkError) as caught:
            self.link(self.felix)
        message = str(caught.exception)
        self.assertIn("Hikaru Nakamura", message)
        self.assertIn("Felix Blohberger", message)
        self.assertIn("--force", message)
        self.assertEqual(PlayerAccount.objects.count(), 0)

    def test_the_right_player_is_accepted(self):
        account, how = self.link(self.hikaru)
        self.assertEqual((account.player, how), (self.hikaru, "as you asked"))

    def test_force_overrides_the_check(self):
        account, _ = self.link(self.felix, force=True)
        self.assertEqual(account.player, self.felix)

    def test_a_profile_without_a_name_is_not_checked(self):
        profile = parse_chesscom_profile(chesscom_profile("hikaru", name=""))
        account, _ = link_chesscom(profile, player_id=self.felix.pk)
        self.assertEqual(account.player, self.felix)

    def test_an_account_that_is_already_linked_is_not_rechecked(self):
        self.link(self.hikaru)
        account, how = link_chesscom(parse_chesscom_profile(chesscom_profile("hikaru")))
        self.assertEqual((account.player, how), (self.hikaru, "was already linked"))


class LichessGuardTests(TestCase):
    def setUp(self):
        self.felix = Player.objects.create(name="Blohberger, Felix", fide_id=100)
        self.hikaru = Player.objects.create(name="Nakamura, Hikaru", fide_id=200)

    def link(self, player, **kwargs):
        profile = parse_lichess_profile(lichess_user("GMHikaru", real_name="Hikaru Nakamura"))
        return link_lichess(profile, fide_id=player.fide_id, **kwargs)

    def test_a_wrong_player_is_refused(self):
        with self.assertRaisesMessage(LinkError, "Lichess says GMHikaru is 'Hikaru Nakamura'"):
            self.link(self.felix)
        self.assertEqual(PlayerAccount.objects.count(), 0)

    def test_the_right_player_and_force(self):
        self.assertEqual(self.link(self.hikaru)[0].player, self.hikaru)
        PlayerAccount.objects.all().delete()
        self.assertEqual(self.link(self.felix, force=True)[0].player, self.felix)

    def test_a_profile_without_a_real_name_is_not_checked(self):
        profile = parse_lichess_profile(lichess_user("GMHikaru"))
        account, _ = link_lichess(profile, fide_id=self.felix.fide_id)
        self.assertEqual(account.player, self.felix)


class CommandGuardTests(TestCase):
    def setUp(self):
        self.felix = Player.objects.create(name="Blohberger, Felix", fide_id=100)

    def run_chesscom(self, *args):
        fake = FakeChesscom(chesscom_profile("hikaru", name="Hikaru Nakamura"), {})
        target = "player.management.commands.sync_chesscom.ChesscomClient"
        with mock.patch(target, return_value=fake):
            call_command("sync_chesscom", "hikaru", "--no-games", *args, stdout=StringIO())

    def run_lichess(self, *args):
        fake = FakeLichess(user=lichess_user("GMHikaru", real_name="Hikaru Nakamura"))
        target = "player.management.commands.sync_lichess.LichessClient"
        with mock.patch(target, return_value=fake):
            call_command(
                "sync_lichess", "GMHikaru", "--no-games", "--no-ratings", *args, stdout=StringIO()
            )

    def test_both_commands_refuse_a_wrong_player_and_explain_how_to_force(self):
        for run in (self.run_chesscom, self.run_lichess):
            with self.subTest(run=run.__name__):
                with self.assertRaisesMessage(CommandError, "--force"):
                    run("--player-id", str(self.felix.pk))
        self.assertEqual(PlayerAccount.objects.count(), 0)

    def test_force_goes_through(self):
        self.run_chesscom("--player-id", str(self.felix.pk), "--force")
        self.assertTrue(
            PlayerAccount.objects.filter(
                player=self.felix, platform=Platform.CHESSCOM, username="hikaru"
            ).exists()
        )
