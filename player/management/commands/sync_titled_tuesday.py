import os
import time

from django.core.management.base import BaseCommand, CommandError

from providers.chesscom import (
    SLUG_RE,
    ChesscomClient,
    ChesscomError,
    ChesscomRateLimited,
    is_titled_tuesday,
    parse_event,
    parse_standings,
)
from providers.chesscom_tournaments import sync_standings, upsert_event
from tournaments.models import Tournament

PAUSE = 1.0  # seconds between two events, to be gentle with Chess.com


class Command(BaseCommand):
    help = "Download the final standings of recent Titled Tuesday events from Chess.com."

    def add_arguments(self, parser):
        parser.add_argument(
            "--recent",
            type=int,
            default=3,
            help="How many of the most recent events already in the database to read (default 3).",
        )
        parser.add_argument(
            "--slug",
            action="append",
            help="A specific event, by the name at the end of its Chess.com address. Repeatable.",
        )
        parser.add_argument(
            "--force", action="store_true", help="Read events whose standings are already stored."
        )

    def make_client(self) -> ChesscomClient:
        return ChesscomClient(
            contact=os.environ.get("CHESSCOM_CONTACT", ""), notify=self.stdout.write
        )

    def handle(self, *args, **options):
        if options["recent"] < 1:
            raise CommandError("--recent must be at least 1.")
        slugs = options["slug"] or self.recent_slugs(options["recent"])
        for slug in slugs:
            if not SLUG_RE.match(slug) or not is_titled_tuesday(slug):
                raise CommandError(f"'{slug}' is not a Titled Tuesday event name.")

        client = self.make_client()
        stored = skipped = 0
        for position, slug in enumerate(slugs):
            if position:
                time.sleep(PAUSE)
            try:
                done = self.sync_event(client, slug, options["force"])
            except ChesscomRateLimited as error:
                raise CommandError(str(error)) from error
            except ChesscomError as error:
                self.stdout.write(self.style.WARNING(f"  skipped {slug}: {error}"))
                done = False
            stored, skipped = stored + done, skipped + (not done)
        self.stdout.write(self.style.SUCCESS(f"Done: {stored} event(s) stored, {skipped} skipped."))

    def recent_slugs(self, count):
        slugs = list(
            Tournament.objects.filter(source="chesscom", external_id__icontains="titled-tuesday")
            .order_by("-start_date")
            .values_list("external_id", flat=True)[:count]
        )
        if not slugs:
            raise CommandError(
                "There are no Titled Tuesday events in the database yet. Run sync_chesscom for a "
                "player who takes part (for example Hikaru), or give an event with --slug."
            )
        return slugs

    def sync_event(self, client, slug, force) -> bool:
        event = parse_event(client.get_tournament(slug))
        if event.start is None:
            self.stdout.write(self.style.WARNING(f"  {slug}: Chess.com gives no start time."))
            return False
        tournament = upsert_event(slug, event)
        if event.status != "finished":
            self.stdout.write(f"  {tournament.name}: not finished yet, skipped.")
            return False
        if tournament.results.exists() and not force:
            self.stdout.write(f"  {tournament.name}: standings already stored (use --force).")
            return False
        if not event.round_urls:
            self.stdout.write(self.style.WARNING(f"  {tournament.name}: no rounds listed."))
            return False

        last_round = client.get_tournament_page(event.round_urls[-1])
        standings = []
        for url in last_round.get("groups") or []:
            standings.extend(parse_standings(client.get_tournament_page(url)))
        if not standings:
            self.stdout.write(self.style.WARNING(f"  {tournament.name}: no standings found."))
            return False

        count = sync_standings(tournament, standings)
        winner = f", winner {event.winner}" if event.winner else ""
        self.stdout.write(f"  {tournament.name}: {count} players{winner}.")
        return True
