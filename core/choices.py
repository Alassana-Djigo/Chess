from django.db import models


class Rhythm(models.TextChoices):
    BLITZ = "B", "Blitz"
    RAPID = "R", "Rapid"
    CLASSICAL = "C", "Classical"
    BULLET = "BL", "Bullet"
