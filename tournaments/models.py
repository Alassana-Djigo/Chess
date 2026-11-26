from django.db import models
from django.db.models import F, Q

from core.choices import Source
from player.models import Player


class Format(models.TextChoices):
    SWISS = "SS", "Swiss System"
    ROUND_ROBIN = "RR", "Round Robin"
    KNOCKOUT = "SE", "Single Elimination/Knockout"
    DOUBLE_ELIMINATION = "ED", "Double Elimination"
    SCHEVENINGEN = "SSG", "Scheveningen System"
    ARENA = "A", "Arena"
    SWISS_ARENA = "SA", "Swiss Arena"
    MATCH = "M", "Match"
    LEAGUE = "LF", "League Format"
    MCMAHON = "McS", "McMahon System"
    TEAM_TOURNAMENT = "TT", "Team Tournament"
    TEAM_MATCH = "TM", "Team Match"
    REPECHAGE = "RS", "Repechage System"


class TournamentStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    ONGOING = "ongoing", "Ongoing"
    FINISHED = "finished", "Finished"


class Tournament(models.Model):
    name = models.CharField(max_length=200)
    format = models.CharField(max_length=3, choices=Format)
    venue = models.CharField(max_length=200, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text="Empty while ongoing.")
    rounds = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=TournamentStatus, default=TournamentStatus.SCHEDULED
    )
    prize = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    source = models.CharField(max_length=10, choices=Source, default=Source.MANUAL)
    external_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-start_date", "name"]
        indexes = [models.Index(fields=["start_date"], name="tournament_start_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="tournament_end_after_start",
            ),
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=~Q(external_id=""),
                name="uniq_tournament_source_external_id",
            ),
        ]

    def __str__(self):
        return self.name


class TournamentResult(models.Model):
    """A player's final score in a tournament. Ties share the same placement."""

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="results")
    player = models.ForeignKey(Player, on_delete=models.PROTECT, related_name="tournament_results")
    points = models.DecimalField(max_digits=5, decimal_places=1)
    placement = models.PositiveIntegerField(help_text="By points only, without tie-breaks.")
    is_winner = models.BooleanField(default=False)

    class Meta:
        ordering = ["tournament", "placement", "player"]
        indexes = [models.Index(fields=["tournament", "placement"], name="result_placement_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["tournament", "player"], name="uniq_result_tournament_player"
            ),
        ]

    def __str__(self):
        return f"{self.player} {self.points} in {self.tournament}"
