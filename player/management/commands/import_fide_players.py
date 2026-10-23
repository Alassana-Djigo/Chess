import time
from datetime import date, datetime
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.choices import Source
from history_rating.models import HistoryRating
from player.fide import FIDE_LIST_URL, READ_ERRORS, FidePlayer, download_list, iter_players
from player.models import Player

BATCH_SIZE = 2000
PLAYER_FIELDS = ["name", "federation", "birth_year", "title", "women_title", "updated_at"]
DEFAULT_DOWNLOAD = "players_list_xml.zip"


def import_batch(players: list[FidePlayer], period: date) -> tuple[int, int, int]:
    """Upsert players and their FIDE ratings for `period`.

    Returns (players written, of which new, ratings written). Running it again with the same
    data changes nothing, and with newer data it updates the existing rows.
    """
    unique = {player.fide_id: player for player in players}  # a repeated id keeps the last one
    ids = list(unique)
    with transaction.atomic():
        existing = set(Player.objects.filter(fide_id__in=ids).values_list("fide_id", flat=True))
        Player.objects.bulk_create(
            [
                Player(
                    fide_id=p.fide_id,
                    name=p.name,
                    federation=p.federation,
                    birth_year=p.birth_year,
                    title=p.title,
                    women_title=p.women_title,
                )
                for p in unique.values()
            ],
            update_conflicts=True,
            unique_fields=["fide_id"],
            update_fields=PLAYER_FIELDS,
        )
        pks = dict(Player.objects.filter(fide_id__in=ids).values_list("fide_id", "pk"))
        ratings = [
            HistoryRating(
                player_id=pks[p.fide_id],
                source=Source.FIDE,
                time_category=category,
                rating_date=period,
                rating=value,
            )
            for p in unique.values()
            for category, value in p.ratings.items()
        ]
        HistoryRating.objects.bulk_create(
            ratings,
            update_conflicts=True,
            unique_fields=["player", "source", "time_category", "rating_date"],
            update_fields=["rating"],
        )
    return len(unique), len(unique) - len(existing), len(ratings)


class Command(BaseCommand):
    help = "Import players and their ratings from the monthly FIDE rating list."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=Path,
            help="Local .zip or .xml from FIDE. Without it, the current list is downloaded.",
        )
        parser.add_argument(
            "--period",
            help="Month the list belongs to, as YYYY-MM. Default: the current month.",
        )
        parser.add_argument(
            "--min-rating",
            type=int,
            default=0,
            help="Only import players with at least one rating of this value or more.",
        )
        parser.add_argument(
            "--limit", type=int, help="Stop after importing this many players (for quick trials)."
        )

    def handle(self, *args, **options):
        period = self.parse_period(options["period"])
        path = Path(options["file"]) if options["file"] else self.download()
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        min_rating, limit = options["min_rating"], options["limit"]
        started = time.monotonic()
        seen = accepted = written = new = ratings = batches = 0
        batch: list[FidePlayer] = []

        def flush():
            nonlocal batch, written, new, ratings, batches
            if not batch:
                return
            count, created, rating_count = import_batch(batch, period)
            written, new, ratings = written + count, new + created, ratings + rating_count
            batches += 1
            batch = []
            if batches % 10 == 0:
                self.stdout.write(f"  {written:,} players so far...")

        try:
            for player in iter_players(path):
                seen += 1
                if min_rating and max(player.ratings.values(), default=0) < min_rating:
                    continue
                batch.append(player)
                accepted += 1
                if len(batch) >= BATCH_SIZE:
                    flush()
                if limit and accepted >= limit:
                    break
            flush()
        except READ_ERRORS as error:
            raise CommandError(
                f"Could not read {path}: {error}. Players imported before the error were "
                "kept; run the command again with a complete file."
            ) from error

        elapsed = time.monotonic() - started
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {written:,} players ({new:,} new), {ratings:,} ratings for "
                f"{period:%Y-%m}; {seen:,} players read in {elapsed:.1f}s."
            )
        )

    def parse_period(self, value: str | None) -> date:
        if value is None:
            return date.today().replace(day=1)
        try:
            return datetime.strptime(value, "%Y-%m").date()
        except ValueError:
            raise CommandError("--period must look like 2026-10 (year-month).") from None

    def download(self) -> Path:
        destination = Path(settings.BASE_DIR) / "data" / DEFAULT_DOWNLOAD
        self.stdout.write(f"Downloading {FIDE_LIST_URL} ...")
        try:
            return download_list(destination)
        except requests.RequestException as error:
            raise CommandError(
                f"Could not download the FIDE list ({error}). Download it manually from "
                "https://ratings.fide.com/download_lists.phtml and pass it with --file."
            ) from error
