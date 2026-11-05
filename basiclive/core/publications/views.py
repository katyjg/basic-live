from django.utils.safestring import mark_safe
from django.views.generic import DetailView, list
from itemlist.views import ItemListView

from basiclive.core.publications.conf import settings
from basiclive.utils import filters
from basiclive.utils.mixins import AdminRequiredMixin
from . import models

PDB_URL_TEMPLATE = settings.PDB_URL_TEMPLATE
PDB_IMAGE_URL_TEMPLATE = settings.PDB_IMAGE_URL_TEMPLATE
YEAR_FILTER_START = settings.YEAR_FILTER_START


class PubEntryList(AdminRequiredMixin, ItemListView):
    template_name = 'publications/list.html'
    model = models.Publication
    list_filters = [
        'created', 'modified',
        filters.StartYearFilter('published'),
        filters.EndYearFilter('published'),
        filters.MonthFilter('published'),
        filters.QuarterFilter('published'),
        'tags'
    ]
    list_columns = ['citation', 'published', 'journal']
    list_search = ['title', 'main_title', 'author_names', 'code', 'comments', 'journal__title', 'funders__name']
    list_transforms = {
        'citation': lambda x, y: mark_safe(x),
        'published': lambda x, y: x.strftime('%Y/%b')
    }
    list_styles = {
        'citation': 'w-70',

    }
    ordering = ['-published']
    paginate_by = 16
    page_title = 'Publication Entries'


class PDBEntryList(AdminRequiredMixin, ItemListView):
    template_name = 'publications/list.html'
    model = models.Deposition
    list_filters = [
        'created', 'modified',
        filters.YearFilter('released'),
        filters.MonthFilter('released'),
        'tags'
    ]
    list_columns = ['id', 'code', 'released', 'title', 'resolution', 'deposited', ]
    list_search = ['title', 'authors', 'code', 'reference__title']
    list_styles = {
        'title': 'w-65',
    }
    ordering = ['-released']
    paginate_by = 16
    page_title = 'PDB Depositions'
    link_field = 'code'
    link_url = 'pdb-entry-detail'
    link_kwarg = 'code'
    link_attr = 'data-modal-url'


class PDBDetail(AdminRequiredMixin, DetailView):
    model = models.Deposition
    template_name = 'publications/pdb-detail.html'
    slug_field = 'code'
    slug_url_kwarg = 'code'

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        code = self.kwargs.get(self.slug_url_kwarg)
        if code:
            obj = queryset.filter(code__iexact=code).first()
            if obj:
                return obj
        return super().get_object(queryset=queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        code = self.object.code
        context['pdb_url'] = settings.PDB_URL_TEMPLATE.format(code)
        context['image_url'] = settings.PDB_IMAGE_URL_TEMPLATE.format(code.lower())
        return context


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
    template_name = 'publications/list.html'
    model = models.SubjectArea
    list_filters = ['created', 'modified']
    list_columns = ['id', 'name', 'code', 'parent__name', ]
    list_search = ['name', 'description', 'code']
    ordering = ['code']
    paginate_by = 16
    page_title = 'Subject Areas'


class JournalList(AdminRequiredMixin, ItemListView):
    template_name = 'publications/list.html'
    model = models.Journal
    list_filters = ['created', 'modified']
    list_columns = ['id', 'title', 'short_name', 'publisher', 'codes']
    list_search = ['short_name', 'title', 'codes', 'publisher']
    list_transforms = {
        'codes': lambda codes, obj: mark_safe(f"<span class='no-wrap'>{" / ".join(codes)}</span>")
    }
    paginate_by = 16
    page_title = 'Journals'

