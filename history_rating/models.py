from django.db import models

from core.choices import Source, TimeCategory
from player.models import Player


class HistoryRating(models.Model):
    """A player's rating in one rating pool on one date.

    FIDE, Lichess and Chess.com ratings are different scales, so `source` is part of the key.
    """

    player = models.ForeignKey(Player, on_delete=models.PROTECT, related_name="rating_history")
    source = models.CharField(max_length=10, choices=Source)
    time_category = models.CharField(max_length=10, choices=TimeCategory)
    rating_date = models.DateField()
    rating = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["-rating_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["player", "source", "time_category", "rating_date"],
                name="uniq_rating_snapshot",
            )
        ]

    def __str__(self):
        return f"{self.player} - {self.rating_date}: {self.rating}"
