from django.test import TestCase
from django.urls import reverse

from core.choices import Source, TimeCategory
from history_rating.models import HistoryRating
from player.models import Platform, Player, PlayerAccount


class AccountsNoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Player.objects.create(name="Carlsen, Magnus", is_active=True)
        cls.b = Player.objects.create(name="Nakamura, Hikaru", is_active=True)

    def page(self):
        return self.client.get(reverse("versus", args=[self.a.pk, self.b.pk]))

    def rate(self, player, source, rating):
        HistoryRating.objects.create(
            player=player,
            source=source,
            time_category=TimeCategory.BLITZ,
            rating_date="2026-10-01",
            rating=rating,
        )

    def test_it_lists_the_linked_accounts_of_each_player(self):
        PlayerAccount.objects.create(
            player=self.a, platform=Platform.LICHESS, username="DrNykterstein"
        )
        PlayerAccount.objects.create(player=self.b, platform=Platform.CHESSCOM, username="hikaru")
        response = self.page()
        self.assertContains(response, "Magnus: Lichess (DrNykterstein)")
        self.assertContains(response, "Hikaru: Chess.com (hikaru)")

    def test_a_player_without_accounts_says_none(self):
        self.assertContains(self.page(), "Magnus: nenhuma; Hikaru: nenhuma.")

    def test_one_sided_online_rows_are_explained(self):
        self.rate(self.b, Source.CHESSCOM, 3300)
        self.assertContains(self.page(), "não tem conta ligada nessa plataforma")

    def test_no_explanation_when_both_sides_have_data(self):
        self.rate(self.a, Source.CHESSCOM, 3200)
        self.rate(self.b, Source.CHESSCOM, 3300)
        self.assertNotContains(self.page(), "não tem conta ligada nessa plataforma")

    def test_no_online_data_means_no_explanation(self):
        self.assertNotContains(self.page(), "não tem conta ligada nessa plataforma")


class AvatarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Player.objects.create(name="Carlsen, Magnus")
        cls.b = Player.objects.create(name="Nakamura, Hikaru")

    def page(self):
        return self.client.get(reverse("versus", args=[self.a.pk, self.b.pk]))

    def test_no_photo_means_no_image(self):
        self.assertNotContains(self.page(), "<img")

    def test_the_photo_of_an_account_is_shown(self):
        PlayerAccount.objects.create(
            player=self.a,
            platform=Platform.CHESSCOM,
            username="MagnusCarlsen",
            avatar_url="https://images.example.com/magnus.png",
        )
        response = self.page()
        self.assertContains(response, 'src="https://images.example.com/magnus.png"')
        self.assertContains(response, 'referrerpolicy="no-referrer"')
        self.assertContains(response, 'class="portrait"', count=1)

    def test_accounts_without_a_photo_are_skipped(self):
        PlayerAccount.objects.create(player=self.a, platform=Platform.LICHESS, username="Mag")
        PlayerAccount.objects.create(
            player=self.a,
            platform=Platform.CHESSCOM,
            username="Magnus",
            avatar_url="https://images.example.com/m.png",
        )
        self.assertContains(self.page(), "https://images.example.com/m.png")
