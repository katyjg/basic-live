from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.messages.views import SuccessMessageMixin
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils import dateformat, timezone
from django.views.generic import edit, detail
from itemlist.views import ItemListView

from basiclive.core.lims import forms, stats
from basiclive.core.lims.models import Project, ActivityLog

from basiclive.utils import filters
from basiclive.accounts.ldap import slap
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
    tool_template = "lims/tools-access.html"
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
    form_class = forms.AccessForm
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


class ProjectList(AdminRequiredMixin, ItemListView):
    model = Project
    paginate_by = 25
    template_name = "lims/user-list.html"
    list_filters = ['created', 'modified', 'kind', 'designation']
    list_columns = ['username', 'contact_person', 'contact_phone', 'contact_email', 'kind']
    list_search = [
        'username', 'contact_person', 'contact_phone', 'contact_email', 'city', 'province', 'country',
        'department', 'organisation'
    ]
    link_url = 'user-detail'
    link_kwarg = 'username'
    add_url = 'new-project'
    add_ajax = True
    ordering = ['name']


class UserDetail(AdminRequiredMixin, detail.DetailView):
    model = Project
    template_name = "lims/entries/user-info.html"

    def get_object(self, **kwargs):
        return Project.objects.get(username=self.kwargs.get('username'))


class UserStats(UserDetail):
    template_name = "lims/entries/user.html"
    page_title = "User Profile"

    def get_object(self, **kwargs):
        return Project.objects.get(username=self.kwargs.get('username'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = stats.project_stats(self.object)
        return context


class ProjectCreate(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.CreateView):
    form_class = forms.NewProjectForm
    template_name = "modal/form.html"
    model = Project
    success_url = reverse_lazy('user-list')
    success_message = "New Account '%(username)s' has been created."

    def form_valid(self, form):
        data = form.cleaned_data
        user_info = {
            k: data.get(k, '')
            for k in ['username', 'password', 'first_name', 'last_name']
            if k in data
        }
        # Make sure user with username does not already exist
        if User.objects.filter(username=user_info.get('username')).exists():
            user_info.pop('username', '')
        ldap = slap.Directory()
        info = ldap.add_user(user_info)
        info['name'] = info.get('username')
        for k in ['contact_email', 'contact_person', 'contact_phone']:
            info[k] = data.get(k, '')

        # create local user
        response = super().form_valid(form)
        info_msg = 'New Account {} added'.format(self.object)

        ActivityLog.objects.log_activity(
            self.request, self.object, ActivityLog.TYPE.CREATE, info_msg
        )
        # messages are simply passed down to the template via the request context
        return response


class ProjectDelete(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.DeleteView):
    template_name = "modal/delete.html"
    model = User
    success_url = reverse_lazy('user-list')
    success_message = "Account has been deleted"

    def get_object(self, *kwargs):
        obj = self.model.objects.get(username=self.kwargs.get('username'))
        return obj

    def get_context_data(self, **kwargs):
        context = super(ProjectDelete, self).get_context_data(**kwargs)
        context['form_action'] = reverse_lazy('user-delete', kwargs={'username': self.object.username})
        return context

    def delete(self, *args, **kwargs):
        obj = self.get_object()
        ldap = slap.Directory()
        ldap.delete_user(obj.username)
        obj.delete()
        self.success_message = "{} account has been deleted".format(kwargs.get('username'))
        return JsonResponse({'url': self.success_url}, safe=False)


def record_logout(sender, user, request, **kwargs):
    """ user logged outof the system """
    ActivityLog.objects.log_activity(request, user, ActivityLog.TYPE.LOGOUT, '{} logged-out'.format(user.username))


def record_login(sender, user, request, **kwargs):
    """ Login a user into the system """
    if user.is_authenticated:
        ActivityLog.objects.log_activity(request, user, ActivityLog.TYPE.LOGIN, '{} logged-in'.format(user.username))
        last_login = ActivityLog.objects.last_login(request)
        if last_login is not None:
            last_host = last_login.ip_number
            message = 'Your previous login was on {date} from {ip}.'.format(
                date=dateformat.format(timezone.localtime(last_login.created), 'M jS @ P'),
                ip=last_host)
            messages.info(request, message)
        elif not request.user.is_staff:
            message = 'You are logging in for the first time. Please make sure your profile is updated.'
            messages.info(request, message)


user_logged_in.connect(record_login)
user_logged_out.connect(record_logout)
