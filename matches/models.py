from django.db import models
from player.models import Jogador
from tournaments.models import Tournament
from core.choices import Rhythm

OUTCOME = [
    ('1-0', 'White wins'),
    ('0-1', 'Black wins'),
    ('1/2-1/2', 'Draw')
]

class Match(models.Model):
    player_white = models.ForeignKey(Jogador, on_delete=models.PROTECT, related_name= 'white_matches')
    player_black = models.ForeignKey(Jogador, on_delete=models.PROTECT, related_name= 'black_matches')
    tournament = models.ForeignKey(Tournament, on_delete=models.SET_NULL, related_name= 'matches', null=True, blank=True)
    outcome = models.CharField(choices=OUTCOME, max_length=7)
    time_control = models.CharField(max_length=2, choices=Rhythm)
    online = models.BooleanField(default=False)
    date = models.DateField()
    location = models.CharField(max_length=80, blank=True, null=True)

    def __str__(self):
        return f"{self.player_white} vs {self.player_black} - {self.date}"
