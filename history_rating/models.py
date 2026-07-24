from django.db import models
from player.models import Jogador
from core.choices import Rhythm

class HistoryRating(models.Model):
    player = models.ForeignKey(Jogador, on_delete=models.PROTECT, related_name='rating_history')
    time_control = models.CharField(max_length=2, choices=Rhythm)
    rating_date = models.DateField()
    rating = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.player} - {self.rating_date}: {self.rating}"