from django.db import models


class TimeCategory(models.TextChoices):
    BULLET = "bullet", "Bullet"
    BLITZ = "blitz", "Blitz"
    RAPID = "rapid", "Rapid"
    CLASSICAL = "classical", "Classical"


class Outcome(models.TextChoices):
    WHITE_WINS = "1-0", "White wins"
    BLACK_WINS = "0-1", "Black wins"
    DRAW = "1/2-1/2", "Draw"
    ONGOING = "*", "In progress"


class Source(models.TextChoices):
    """Where a record comes from. Together with `external_id` it prevents duplicates on import."""

    MANUAL = "manual", "Manual"
    FIDE = "fide", "FIDE"
    LICHESS = "lichess", "Lichess"
    CHESSCOM = "chesscom", "Chess.com"
