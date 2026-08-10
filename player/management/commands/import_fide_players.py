from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Importar jogadores a partir da lista oficial de rating da FIDE"

    def handle(self, *args, **options):
        self.stdout.write("comando funcionando!")