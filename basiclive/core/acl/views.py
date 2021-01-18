from django.conf import settings

from django.contrib.auth import get_user_model
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy

from django.views.generic import edit, detail
from itemlist.views import ItemListView

from .forms import AccessForm

from basiclive.utils import filters
from basiclive.utils.mixins import AsyncFormMixin, AdminRequiredMixin, PlotViewMixin

from . import models

User = get_user_model()


def format_beamlines(value, record):
    return ', '.join(record.beamline.values_list('acronym', flat=True))


class AccessListView(AdminRequiredMixin, ItemListView):
    model = models.AccessList
    list_filters = ['beamline', 'active']
    list_columns = ['name', 'description', 'current_users', 'allowed_users', 'address', 'beamlines', 'active']
    list_transforms = {'beamlines': format_beamlines}
    list_search = ['name', 'description']
    tool_template = "acl/tools-access.html"
    link_url = 'access-edit'
    link_kwarg = 'address'
    link_attr = 'data-form-link'
    ordering = ['name']
    template_name = "lims/list.html"
    page_title = 'Remote Access'

    def get_list_columns(self):
        if settings.LIMS_USE_SCHEDULE and 'current_users' in self.list_columns:
            self.list_columns[self.list_columns.index('current_users')] = 'scheduled_users'
        return self.list_columns


class AccessEdit(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = AccessForm
    template_name = "modal/form.html"
    model = models.AccessList
    success_url = reverse_lazy('access-list')
    success_message = "Remote access list has been updated."
    allowed_roles = ['owner', 'admin']
    admin_roles = ['admin']

    def get_object(self, queryset=None):
        return self.model.objects.get(address=self.kwargs.get('address'))


class RemoteConnectionList(AdminRequiredMixin, ItemListView):
    model = models.Access
    list_columns = ['user', 'name', 'userlist', 'status', 'created', 'end']
    list_filters = ['created', filters.YearFilterFactory('created', reverse=True), 'userlist', 'status']
    list_search = ['user__username', 'name', 'status', 'userlist__name', 'created']
    ordering = ['-created']
    template_name = "lims/list.html"
    link_url = 'connection-detail'
    link_attr = 'data-link'
    page_title = 'Remote Connections'
    plot_url = reverse_lazy("connection-stats")
    paginate_by = 100


class RemoteConnectionStats(PlotViewMixin, RemoteConnectionList):
    plot_fields = {'user__kind__name': {}, 'userlist__name': {}, 'status': {}}
    date_field = 'created'
    list_url = reverse_lazy("connection-list")


class RemoteConnectionDetail(AdminRequiredMixin, detail.DetailView):
    model = models.Access
    template_name = "lims/entries/connection.html"
