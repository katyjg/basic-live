from django.views.generic import TemplateView, list

from itemlist.views import ItemListView
from basiclive.utils import filters
from basiclive.utils.mixins import AdminRequiredMixin
from . import models, stats


class PubEntryList(AdminRequiredMixin, ItemListView):
    template_name = 'publications/list.html'
    model = models.Publication
    list_filters = [
        'created', 'modified',
        filters.YearFilterFactory('published', start=2004, reverse=True),
        filters.MonthFilterFactory('published'),
        filters.QuarterFilterFactory('published'),
        'tags'
    ]
    list_columns = ['id', 'published', 'cite', 'metrics__citations', 'metrics__mentions', 'journal__metrics__impact_factor']
    list_search = ['title', 'main_title', 'authors', 'code', 'comments', 'journal__title', 'funders__name']
    list_headers = {
        'journal__metrics__impact_factor': "Journal Impact Factor",
        'metrics__mentions': "Mentions",
        'metrics__citations': "Citations",
    }
    list_styles = {
        'cite': 'w-75',
    }
    ordering = ['-published']
    paginate_by = 25
    page_title = 'Publication Entries'


class PDBEntryList(AdminRequiredMixin, ItemListView):
    template_name = 'publications/list.html'
    model = models.Deposition
    list_filters = [
        'created', 'modified',
        filters.YearFilterFactory('released'),
        filters.MonthFilterFactory('released'),
        'tags'
    ]
    list_columns = ['id', 'code', 'released', 'title', 'resolution', 'deposited', ]
    list_search = ['title', 'authors', 'code', 'reference__title']
    list_styles = {
        'title': 'w-75',
    }
    ordering = ['-released']
    paginate_by = 25
    page_title = 'PDB Depositions'


class PDBEntryText(list.ListView):
    model = models.Deposition

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        field_map = {
            'PDB_ID': 'code',
            'STRUCTURE TITLE': 'title',
            'DEPOSITION DATE': 'deposited',
            'RELEASE DATE': 'released',
            'AUTHORS': 'authors'
        }
        header = ['PDB_ID', 'STRUCTURE TITLE', 'DEPOSITION DATE', 'RELEASE DATE', 'AUTHORS']
        context['header'] = '\t'.join(header)
        context['text'] = '\n'.join(
            ['\t'.join([str(getattr(dep, field_map[f])) for f in header]) for dep in self.object_list]
        )
        return context


class SubjectAreasList(AdminRequiredMixin, ItemListView):
    template_name = 'publications/templates/publications/list.html'
    model = models.SubjectArea
    list_filters = ['created', 'modified']
    list_columns = ['id', 'name', 'code', 'parent__name', ]
    list_search = ['name', 'description', 'code']
    ordering = ['code']
    paginate_by = 25
    page_title = 'PDB Depositions'


class JournalList(AdminRequiredMixin, ItemListView):
    template_name = 'publications/templates/publications/list.html'
    model = models.Journal
    list_filters = ['created', 'modified']
    list_columns = ['id', 'title', 'short_name', 'publisher', 'codes', 'metrics__impact_factor']
    list_search = ['short_name', 'title', 'codes', 'publisher']
    paginate_by = 25
    page_title = 'Journals'


class Statistics(AdminRequiredMixin, TemplateView):
    template_name = "publications/templates/publications/statistics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tag = self.kwargs.get('tag')
        year = self.kwargs.get('year')
        period = 'month' if year else 'year'

        context['year'] = year
        context['tag'] = tag
        context['tags'] = models.Tag.objects.values_list('name', flat=True)
        context['years'] = stats.get_publications_periods(period='year')
        context['report'] = stats.publication_stats(period=period, year=year, tag=tag)
        return context

    def page_title(self):
        if self.kwargs.get('year'):
            return '{} Publication Metrics'.format(self.kwargs['year'])
        else:
            return 'Publication Metrics'