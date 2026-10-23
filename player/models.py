from django.db import models

TITLE = [
    ("GM", "Grandmaster"),
    ("IM", "International Master"),
    ("FM", "FIDE Master"),
    ("CM", "Candidate Master"),
    ("X", "No Title"),
    ("WGM", "Woman Grandmaster"),
    ("WIM", "Woman International Master"),
    ("WFM", "Woman Fide Master"),
    ("WCM", "Woman Candidate Master"),
]


class Jogador(models.Model):
    name = models.CharField(max_length=50)
    date_birth = models.DateField()
    title = models.CharField(max_length=3, choices=TITLE, default="X")
    federation = models.CharField(max_length=80)
    id_fide = models.PositiveIntegerField(blank=True, unique=True, null=True)

    def __str__(self):
        return self.name
