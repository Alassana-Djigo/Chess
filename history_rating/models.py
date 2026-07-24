from django.db import models
from player.models import Jogador

RHYTHM = [
    ("B", "Blitz"),
    ("R", "Rapid"),
    ("C", "Classical"),
    ("BL", "Bullet")
]


class HistoryRating(models.Model):
    player = models.ForeignKey(Jogador, on_delete=models.CASCADE, related_name='rating_history')
    time_control = models.CharField(max_length=2, choices=RHYTHM)
    rating_date = models.DateField()
    rating = models.PositiveIntegerField()

    def __str__(self):
        return self.player