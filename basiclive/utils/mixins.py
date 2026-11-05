import warnings
from urllib import parse

from crisp_modals.views import AjaxFormMixin
from django import http
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpRequest
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from basiclive.utils.conf import settings
from ..utils.stats import generic_stats

TEMP_PREFIX = settings.PDF_TEMP_PREFIX
CACHE_PREFIX = settings.PDF_CACHE_PREFIX
CACHE_TIMEOUT = settings.PDF_CACHE_TIMEOUT


def is_ajax(request: HttpRequest) -> bool:
    """
    https://stackoverflow.com/questions/63629935
    """
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or request.accepts("application/json")
    )


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Mixin to allow access through a view only if the user is a superuser.
    Can be used with any View.
    """
    def test_func(self):
        return self.request.user.is_superuser


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Mixin to allow access through a view only if the user is a staff member.
    Can be used with any View.
    """
    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser


@method_decorator(csrf_exempt, name='dispatch')
class AuthenticationRequiredMixin(object):
    """
    Mixin to verify that the user is logged-in without any redirects
    """

    def dispatch(self, request, *args, **kwargs):
        if hasattr(request, 'user') and request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        else:
            return http.HttpResponseForbidden()


class AsyncFormMixin(AjaxFormMixin):
    """
    Deprecated: use crisp_modals.views.ModalCreateView, ModalUpdateView, ModalDeleteView, etc.
    """
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "AsyncFormMixin is deprecated and will be removed in a future release. "
            "Use ModalView classes from crisp_modals.views instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)


class PlotViewMixin:
    template_name = "lims/list-plots.html"
    plot_fields = []
    date_field = None
    paginate_by = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = self.get_metrics()
        context['active_filters'] = self.get_active_filters()
        return context

    def get_plot_fields(self):
        return self.plot_fields

    def get_active_filters(self):
        filter_specs, has_filters, filter_use_distinct = self.get_filters()
        qsl = self.get_query_string()
        if self.date_field:
            for part in ['year', 'month', 'day', 'quarter']:
                qsl = qsl.replace(f'{self.date_field}_{part}', f'{self.date_field}__{part}')

            # update time range filters
            for part in ['since', 'until', 'before', 'after']:
                lookup_opr = {
                    'since': 'year__gte',
                    'until': 'year__lte',
                    'before': 'year__lt',
                    'after': 'year__gt'
                }.get(part)
                qsl = qsl.replace(f'{self.date_field}_{part}', f'{self.date_field}__{lookup_opr}')
        return dict(parse.parse_qsl(qsl.strip('?')))

    def get_metrics(self):
        return generic_stats(self.get_queryset(), self.get_plot_fields(), self.date_field)
