from django.core.management.base import BaseCommand

from basiclive.core.publications.utils import update_journal_metrics, update_publication_metrics, fetch_journal_metrics, update_funders

class Command(BaseCommand):
    help = 'Updates journal and publication metrics, and funders'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int)

    def handle(self, *args, **options):
        year = options.get('year', None)

        new_jmetrics = fetch_journal_metrics(year)
        print("FETCHED JOURNAL METRICS: {}".format(new_jmetrics))
        jmetrics = update_journal_metrics(year)
        print("UPDATED JOURNAL METRICS: {}".format(jmetrics))
        pmetrics = update_publication_metrics(year)
        print("UPDATED PUBLICATION METRICS: {}".format(pmetrics))
        update_funders()
