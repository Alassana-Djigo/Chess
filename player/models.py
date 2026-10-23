from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower


class Title(models.TextChoices):
    GM = "GM", "Grandmaster"
    IM = "IM", "International Master"
    FM = "FM", "FIDE Master"
    CM = "CM", "Candidate Master"


class WomenTitle(models.TextChoices):
    WGM = "WGM", "Woman Grandmaster"
    WIM = "WIM", "Woman International Master"
    WFM = "WFM", "Woman FIDE Master"
    WCM = "WCM", "Woman Candidate Master"


class Platform(models.TextChoices):
    LICHESS = "lichess", "Lichess"
    CHESSCOM = "chesscom", "Chess.com"


class Player(models.Model):
    """A real person. Their accounts on online platforms live in PlayerAccount."""

    name = models.CharField(max_length=150)
    birth_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1900), MaxValueValidator(2100)],
    )
    federation = models.CharField(
        max_length=3,
        blank=True,
        validators=[RegexValidator(r"^[A-Z]{3}$", "Use the 3-letter FIDE code, e.g. ANG.")],
        help_text="3-letter FIDE federation code, e.g. NOR.",
    )
    fide_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
    title = models.CharField(max_length=3, choices=Title, blank=True)
    women_title = models.CharField(max_length=3, choices=WomenTitle, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PlayerAccount(models.Model):
    """An account of a player on an online platform (a player can have several)."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="accounts")
    platform = models.CharField(max_length=10, choices=Platform)
    username = models.CharField(max_length=64)
    external_id = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("username"), "platform", name="uniq_account_platform_username"
            )
        ]

    def __str__(self):
        return f"{self.username} ({self.get_platform_display()})"
