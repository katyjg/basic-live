from django.core.management.base import BaseCommand

from basiclive.core.publications.utils import fetch_and_update_depositions

class Command(BaseCommand):
    help = 'Fetches PDB depositions from source defined in PDB_SEARCH_URL'

    def handle(self, *args, **options):
        fetch_and_update_depositions()
