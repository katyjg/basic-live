from datetime import datetime
from zoneinfo import ZoneInfo

import msgpack
from django.contrib.auth import get_user_model
from django.contrib.messages.views import SuccessMessageMixin
from django.http import JsonResponse, HttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import edit, detail
from itemlist.views import ItemListView

from crisp_modals.views import ModalUpdateView
from basiclive.utils import filters
from basiclive.utils.mixins import AdminRequiredMixin, PlotViewMixin, AuthenticationRequiredMixin
from basiclive.utils.network import get_client_address
from . import models
from .forms import AccessForm

User = get_user_model()


def format_beamlines(value, record):
    return ', '.join(record.beamline.values_list('acronym', flat=True))


def format_authorized(projects, record):
    badges = []
    for project in projects:
        if project.source == 'schedule':
            css_class = 'badge text-bg-success'
            title = 'Scheduled Access'
        else:
            css_class = 'badge text-bg-warning'
            title = 'Manual Access'
        badges.append(f'<span class="{css_class} badge-md" title="{title}">{escape(project.name.upper())}</span>')
    return ' '.join(badges)


class AccessListView(AdminRequiredMixin, ItemListView):
    model = models.AccessList
    list_filters = ['beamline']
    list_columns = ['name', 'description', 'annotated_projects', 'address', 'beamlines']
    list_headers = {
        'annotated_users': 'Authorized Users',
        'annotated_projects': 'Authorized Users',
    }
    list_transforms = {
        'beamlines': format_beamlines,
        'annotated_users': format_authorized,
        'annotated_projects': format_authorized,
    }
    list_search = ['name', 'description']
    tool_template = "acl/tools-access.html"
    link_url = 'access-edit'
    link_kwarg = 'pk'
    link_attr = 'data-modal-url'
    ordering = ['name']
    template_name = "lims/list.html"
    page_title = 'Access Endpoints'

    def get_queryset(self, *args, **kwargs):
        queryset = super().get_queryset(*args, **kwargs)
        return queryset.filter(active=True)


class AccessEdit(AdminRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = AccessForm
    model = models.AccessList
    success_url = reverse_lazy('access-list')
    success_message = "Access Control List has been updated."
    allowed_roles = ['owner', 'admin']
    admin_roles = ['admin']


class AccessConnectionList(AdminRequiredMixin, ItemListView):
    model = models.Access
    list_columns = ['user', 'name', 'userlist', 'status', 'start_time', 'end_time', 'total_time']
    list_filters = ['start_time', filters.YearFilter('start_time', reverse=True), 'userlist', 'status']
    list_search = ['user__name', 'name', 'status', 'userlist__name', 'start_time']
    ordering = ['-start_time']
    template_name = "lims/list.html"
    link_url = 'access-connection-detail'
    link_attr = 'data-modal-url'
    page_title = 'Access Connections'
    plot_url = reverse_lazy("connection-stats")
    paginate_by = 100


class AccessConnectionStats(PlotViewMixin, AccessConnectionList):
    plot_fields = {'user__kind__name': {}, 'userlist__name': {}, 'status': {}}
    date_field = 'start_time'
    list_url = reverse_lazy("access-connections")


class AccessConnectionDetail(AdminRequiredMixin, detail.DetailView):
    model = models.Access
    template_name = "acl/connection.html"


@method_decorator(csrf_exempt, name='dispatch')
class EndpointList(View):
    """
    Returns list of usernames that should be able to access the remote server referenced by the IP number inferred from
    the request.

    :key: r'^accesslist/$'
    """

    def get(self, request, *args, **kwargs):
        client_addr = get_client_address(request)

        userlist = models.AccessList.objects.active_for_ip(client_addr)

        if userlist:
            return JsonResponse(userlist.authorized_users(), safe=False)
        else:
            return JsonResponse([], safe=False)

    def post(self, request, *args, **kwargs):
        client_addr = get_client_address(request)
        user_list = models.AccessList.objects.active_for_ip(client_addr)

        errors = []

        if user_list:
            connections = msgpack.loads(request.body)

            for connection in connections:
                try:
                    project = models.Project.objects.filter(
                        models.Q(username=connection['project']) | models.Q(name=connection['project'])
                    ).first()
                    if not project:
                        raise models.Project.DoesNotExist()
                    start_time = datetime.fromisoformat(connection['start_time'])
                    end_time = None if not connection.get('end_time') else datetime.fromisoformat(connection['end_time'])
                    name = connection['name']
                    status = {
                        'Finished': models.Access.Status.FINISHED,
                        'Connected': models.Access.Status.CONNECTED,
                        'Failed': models.Access.Status.FAILED,
                        'Disconnected': models.Access.Status.DISCONNECTED,
                    }.get(connection['status'], models.Access.Status.CONNECTED)

                    r, created = models.Access.objects.get_or_create(
                        name=name, userlist=user_list, user=project
                    )

                    r.status = status
                    r.start_time = start_time
                    r.end_time = end_time
                    r.save()

                except models.Project.DoesNotExist:
                    errors.append(f"Project '{connection['project']}' not found.")

            return JsonResponse(user_list.authorized_users(), safe=False)
        else:
            return JsonResponse([], safe=False)


@method_decorator(csrf_exempt, name='dispatch')
class AccessKeys(AuthenticationRequiredMixin, View):
    """
    Returns SSH keys for the user if the remote server referenced by the IP number inferred from
    the request exists and the user is specifically allowed to access the host.

    :key: r'^keys/<username>$'
    """

    def get(self, request, *args, **kwargs):

        client_addr = get_client_address(request)
        user_list = models.AccessList.objects.active_for_ip(client_addr)
        user = User.objects.filter(username=self.kwargs.get('username')).first()

        msg = ''
        if user and user_list and user.username in user_list.authorized_users():
            msg = '\n'.join(user.sshkeys.values_list('key', flat=True)).encode()

        return HttpResponse(msg, content_type='text/plain')
