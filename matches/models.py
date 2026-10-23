from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q

from core.choices import Outcome, Source, TimeCategory
from player.models import Player
from tournaments.models import Tournament


class Match(models.Model):
    player_white = models.ForeignKey(Player, on_delete=models.PROTECT, related_name="white_matches")
    player_black = models.ForeignKey(Player, on_delete=models.PROTECT, related_name="black_matches")
    tournament = models.ForeignKey(
        Tournament, on_delete=models.SET_NULL, related_name="matches", null=True, blank=True
    )
    round = models.PositiveSmallIntegerField(null=True, blank=True)
    board = models.PositiveSmallIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=7, choices=Outcome, default=Outcome.ONGOING)

    time_category = models.CharField(max_length=10, choices=TimeCategory)
    time_base = models.PositiveIntegerField(
        null=True, blank=True, help_text="Base time in seconds."
    )
    time_increment = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Increment per move in seconds."
    )

    online = models.BooleanField(default=False)
    date = models.DateField()
    started_at = models.DateTimeField(null=True, blank=True)
    venue = models.CharField(max_length=200, blank=True)

    pgn = models.TextField(blank=True, help_text="Full PGN, including the moves.")
    eco = models.CharField(
        max_length=3,
        blank=True,
        validators=[RegexValidator(r"^[A-E][0-9]{2}$", "Use an ECO code such as B12.")],
    )
    opening = models.CharField(max_length=120, blank=True)
    white_elo = models.PositiveSmallIntegerField(null=True, blank=True)
    black_elo = models.PositiveSmallIntegerField(null=True, blank=True)

    source = models.CharField(max_length=10, choices=Source, default=Source.MANUAL)
    external_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name_plural = "matches"
        indexes = [
            models.Index(fields=["date"], name="match_date_idx"),
            models.Index(fields=["player_white", "date"], name="match_white_date_idx"),
            models.Index(fields=["player_black", "date"], name="match_black_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(player_white=F("player_black")), name="match_players_differ"
            ),
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=~Q(external_id=""),
                name="uniq_match_source_external_id",
            ),
        ]

    def __str__(self):
        return f"{self.player_white} vs {self.player_black} - {self.date}"
