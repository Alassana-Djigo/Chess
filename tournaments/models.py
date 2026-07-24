from django.db import models

FORMAT = [
    ("SS", "Swiss System"),
    ("RR", "Round Robin"),
    ("SE", "Single Elimination/Knockout"),
    ("ED", "Double Elimination"),
    ("SSG", "Scheveningen System"),
    ("A", "Arena"),
    ("SA", "Swiss Arena"),
    ("M", "Match"),
    ("LF", "League Format"),
    ("McS", "McMahon System"),
    ("TT", "Team Tournament"),
    ("TM", "Team Match"),
    ("RS" ,"Repechage System")
]

class Tournament(models.Model):
    name = models.CharField(max_length=80)
    formate = models.CharField(choices=FORMAT, max_length=20)
    local = models.CharField(max_length=80)
    start_date = models.DateField()
    end_date = models.DateField()
    prize = models.DecimalField(max_digits=9, decimal_places=2, default=0)

    def __str__(self):
        return self.name