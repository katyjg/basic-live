import json
from datetime import timedelta
import requests

from django import http
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.db.models import Count, Q, Case, When, Value, BooleanField, Max
from django.forms.models import model_to_dict
from django.http import JsonResponse, Http404, HttpResponseRedirect, HttpResponseNotAllowed
from django.urls import reverse, reverse_lazy
from django.utils import dateformat, timezone
from django.views.generic import edit, detail, View
from formtools.wizard.views import SessionWizardView
from itemlist.views import ItemListView
from proxy.views import proxy_view


from basiclive.utils import filters
from basiclive.utils.mixins import AsyncFormMixin, AdminRequiredMixin, HTML2PdfMixin, PlotViewMixin
from . import forms, models, stats

DOWNLOAD_PROXY_URL = getattr(settings, 'DOWNLOAD_PROXY_URL', "http://basiclive.core-data/download")
LIMS_USE_SCHEDULE = getattr(settings, 'LIMS_USE_SCHEDULE', False)
LIMS_USE_ACL = getattr(settings, 'LIMS_USE_ACL', False)

if LIMS_USE_SCHEDULE:
    from basiclive.core.schedule.models import AccessType, BeamlineSupport, Beamtime

    MIN_SUPPORT_HOUR = getattr(settings, 'MIN_SUPPORT_HOUR', 0)
    MAX_SUPPORT_HOUR = getattr(settings, 'MAX_SUPPORT_HOUR', 24)

if LIMS_USE_ACL:
    from basiclive.core.acl.models import Access, AccessList


class ProjectDetail(UserPassesTestMixin, detail.DetailView):
    """
    This is the "Dashboard" view. Basic information about the Project is displayed:

    :For superusers, direct to StaffDashboard

    :For Users, direct to project.html, with context:
       - shipments: All Shipments that are Draft, Sent, or On-site, plus Returned shipments to bring the
                    total displayed up to seven.
       - sessions: Any recent Session from any beamline
    """
    model = models.Project
    template_name = "lims/project.html"
    slug_field = 'username'
    slug_url_kwarg = 'username'

    def test_func(self):
        # Allow access to admin or owner
        return self.request.user.is_superuser or self.get_object() == self.request.user

    def get_object(self, *args, **kwargs):
        # inject username in to kwargs if not already present
        if not self.kwargs.get('username'):
            self.kwargs['username'] = self.request.user.username
        return super(ProjectDetail, self).get_object(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        if self.request.user.is_superuser:
            return HttpResponseRedirect(reverse_lazy('staff-dashboard'))

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ProjectDetail, self).get_context_data(**kwargs)
        now = timezone.now()
        one_year_ago = now - timedelta(days=365)
        project = self.request.user
        shipments = project.shipments.filter(
            Q(status__lt=models.Shipment.STATES.RETURNED)
            | Q(status=models.Shipment.STATES.RETURNED, date_returned__gt=one_year_ago)
        ).annotate(
            data_count=Count('containers__samples__datasets', distinct=True),
            report_count=Count('containers__samples__datasets__reports', distinct=True),
            sample_count=Count('containers__samples', distinct=True),
            group_count=Count('groups', distinct=True),
            container_count=Count('containers', distinct=True),
        ).order_by('status', '-date_shipped', '-created').prefetch_related('project')

        if LIMS_USE_SCHEDULE:
            access_types = AccessType.objects.all()
            beamtimes = project.beamtime.filter(end__gte=now, cancelled=False).with_duration().annotate(
                current=Case(When(start__lte=now, then=Value(True)), default=Value(False), output_field=BooleanField())
            ).order_by('-current', 'start')
            context.update(beamtimes=beamtimes, access_types=access_types)

        sessions = project.sessions.filter(
            created__gt=one_year_ago
        ).annotate(
            data_count=Count('datasets', distinct=True),
            report_count=Count('datasets__reports', distinct=True),
            last_record=Max('datasets__end_time'),
            end=Max('stretches__end')
        ).order_by('-end', 'last_record', '-created').with_duration().prefetch_related('project', 'beamline')[:7]

        context.update(shipments=shipments, sessions=sessions)
        return context


class StaffDashboard(AdminRequiredMixin, detail.DetailView):
    """
    This is the "Dashboard" view for superusers only. Basic information is displayed:
       - shipments: Any Shipments that are Sent or On-site
       - automounters: Any active Automounter objects (Beamline/Automounter)
       - adaptors: Any adaptors for loading Containers into a Automounter
       - connections: Any project currently scheduled, connected to a remote access list, or with an active session
       - local contact: Displayed if there is a local contact scheduled
       - user guide: All items, for users and marked staff only
    """

    model = models.Project
    template_name = "lims/staff-dashboard.html"
    slug_field = 'username'
    slug_url_kwarg = 'username'

    def get_object(self, *args, **kwargs):
        # inject username in to kwargs if not already present
        if not self.kwargs.get('username'):
            self.kwargs['username'] = self.request.user.username
        return super().get_object(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        shipments = models.Shipment.objects.filter(
            status__in=(models.Shipment.STATES.SENT, models.Shipment.STATES.ON_SITE)
        ).annotate(
            data_count=Count('containers__samples__datasets', distinct=True),
            report_count=Count('containers__samples__datasets__reports', distinct=True),
            sample_count=Count('containers__samples', distinct=True),
            group_count=Count('groups', distinct=True),
            container_count=Count('containers', distinct=True),
        ).order_by('status', 'project__kind__name', 'project__username', '-date_shipped').prefetch_related('project')

        adaptors = models.Container.objects.filter(
            project__is_superuser=True,
            kind__locations__accepts__isnull=False,
            beamlines__isnull=True,
            status__gt=models.Container.STATES.DRAFT
        ).distinct().order_by('name').select_related('parent')

        beamlines = models.Beamline.objects.all().order_by('name')

        active_sessions = models.Session.objects.filter(stretches__end__isnull=True).annotate(
            data_count=Count('datasets', distinct=True),
            report_count=Count('datasets__reports', distinct=True)).with_duration()

        access_info = []
        connections = []
        sessions = []
        active_access = LIMS_USE_ACL and Access.objects.filter(status__iexact=Access.STATES.CONNECTED) or []
        if LIMS_USE_SCHEDULE:
            context.update(access_types=AccessType.objects.all(),
                           support=BeamlineSupport.objects.filter(date=timezone.localtime().date()).first())
            # Find out who is scheduled to use the beamline
            for bt in Beamtime.objects.filter(start__lte=now, end__gte=now).with_duration():
                bt_sessions = models.Session.objects.filter(project=bt.project, beamline=bt.beamline).filter(
                    Q(stretches__end__isnull=True) | Q(stretches__end__gte=bt.start)).distinct()
                sessions += bt_sessions
                # Check if the scheduled project is currently connected
                bt_conns = LIMS_USE_ACL and active_access.filter(
                    user=bt.project, userlist__pk__in=bt.beamline.access_lists.values_list('pk', flat=True)) or []
                connections += bt_conns

                access_info.append({
                    'user': bt.project,
                    'beamline': bt.beamline.acronym,
                    'beamtime': bt,
                    'sessions': bt_sessions,
                    'connections': bt_conns
                })

        # Check who has an active session
        for session in active_sessions.exclude(pk__in=[s.pk for s in sessions]):
            ss_conns = LIMS_USE_ACL and active_access.filter(
                user=session.project, userlist__pk__in=session.beamline.access_lists.values_list('pk', flat=True)) or []
            connections += ss_conns
            access_info.append({
                'user': session.project,
                'beamline': session.beamline.acronym,
                'sessions': [session],
                'connections': ss_conns
            })
        # Users remotely connected, but not scheduled and without an active session
        if LIMS_USE_ACL:
            for user in active_access.exclude(pk__in=[c.pk for c in connections]).values_list('user', flat=True).distinct():
                user_conns = active_access.exclude(pk__in=[c.pk for c in connections]).filter(user__pk=user)
                access_info.append({
                    'user': models.Project.objects.get(pk=user),
                    'beamline': '/'.join(
                        [bl for bl in user_conns.values_list('userlist__beamline__acronym', flat=True).distinct() if bl]
                    ),
                    'connections': user_conns
                })

        for i, conn in enumerate(access_info):
            access_info[i]['shipments'] = shipments.filter(project=conn['user']).count()
            access_info[i]['connections'] = LIMS_USE_ACL and {
                access.name: access_info[i]['connections'].filter(userlist=access)
                for access in AccessList.objects.filter(pk__in=access_info[i]['connections'].values_list('userlist__pk', flat=True)).distinct()
            } or {}

        context.update(connections=access_info, adaptors=adaptors, shipments=shipments, beamlines=beamlines)
        return context


class ProjectReset(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    template_name = "lims/forms/project-reset.html"
    model = models.Project
    success_message = "Account API key reset"
    fields = ("key", )

    def get_success_url(self):
        return self.object.get_absolute_url()

    def get_object(self, *kwargs):
        obj = self.model.objects.get(username=self.kwargs.get('username'))
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_action'] = reverse_lazy('project-reset', kwargs={'username': self.object.username})
        return context


class ProjectProfile(UserPassesTestMixin, detail.DetailView):
    model = models.Project
    template_name = "lims/entries/project-profile.html"
    slug_field = 'username'
    slug_url_kwarg = 'username'

    def test_func(self):
        # Allow access to admin or owner
        return self.request.user.is_superuser or self.get_object() == self.request.user

    def get_object(self, *args, **kwargs):
        # inject username in to kwargs if not already present
        if not self.kwargs.get('username'):
            self.kwargs['username'] = self.request.user
        return super().get_object(*args, **kwargs)


class ProjectStatistics(ProjectProfile):
    template_name = "lims/entries/project-statistics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = stats.project_stats(self.object)
        return context


class OwnerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Mixin to limit access to the owner of an object (or superusers).
    Must be used with an object-based View (e.g. DetailView, EditView)
    """
    owner_field = 'project'

    def test_func(self):
        return self.request.user.is_superuser or getattr(self.get_object(), self.owner_field) == self.request.user


class ProjectEdit(UserPassesTestMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.ProjectForm
    template_name = "modal/form.html"
    model = models.Project
    success_message = "Profile has been updated."

    def get_object(self):
        return models.Project.objects.get(username=self.kwargs.get('username'))

    def test_func(self):
        """Allow access to admin or owner"""
        return self.request.user.is_superuser or self.get_object() == self.request.user

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse_lazy('project-profile', kwargs={'username': self.kwargs['username']})


class ProjectLabels(AdminRequiredMixin, HTML2PdfMixin, detail.DetailView):
    template_name = "lims/pdf/return_labels.html"
    model = models.Project
    slug_field = 'username'
    slug_url_kwarg = 'username'

    def get_template_name(self):
        return self.template_name

    def get_template_context(self):
        object = self.get_object()
        context = {
            'project': object,
            'shipment': object,
            'admin_project': models.Project.objects.filter(is_superuser=True).first()
        }
        return context


class ListViewMixin(LoginRequiredMixin):
    paginate_by = 25
    template_name = "lims/list.html"
    link_data = False
    show_project = True

    def get_list_columns(self):
        columns = super().get_list_columns()
        if self.request.user.is_superuser and self.show_project:
            return ['project__name'] + columns
        return columns

    def get_queryset(self):
        selector = {}
        if not self.request.user.is_superuser:
            selector = {'project': self.request.user}
        return super().get_queryset().filter(**selector)

    def page_title(self):
        return self.model._meta.verbose_name_plural.title()


class DetailListMixin(OwnerRequiredMixin):
    extra_model = None
    add_url = None
    list_filters = []
    paginate_by = 25

    def get_context_data(self, **kwargs):
        c = super(DetailListMixin, self).get_context_data(**kwargs)
        c['object'] = self.get_object()
        c['total_objects'] = self.get_queryset().count()
        return c

    def get_object(self):
        return self.extra_model.objects.get(pk=self.kwargs['pk'])

    def get_queryset(self):
        super(DetailListMixin, self).get_queryset()
        return self.get_object().samples.all()


class ShipmentList(ListViewMixin, ItemListView):
    model = models.Shipment
    list_filters = ['created', 'status']
    list_columns = ['id', 'name', 'date_shipped', 'carrier', 'num_containers', 'status']
    list_search = ['project__username', 'project__name', 'name', 'comments', 'status']
    link_url = 'shipment-detail'
    link_data = False
    ordering = ['status', '-modified']
    paginate_by = 25

    def get_queryset(self):
        if self.request.user.is_superuser:
            return super(ShipmentList, self).get_queryset().filter(
                status__gte=models.Shipment.STATES.SENT)
        return super(ShipmentList, self).get_queryset()


class ShipmentDetail(OwnerRequiredMixin, detail.DetailView):
    model = models.Shipment
    template_name = "lims/entries/shipment.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['automounters'] = {
            container.pk: container.automounter() for container in self.object.containers.all()
        }
        return ctx


class ShipmentLabels(HTML2PdfMixin, ShipmentDetail):
    template_name = "lims/pdf/send_labels.html"

    def get_template_name(self):
        if self.request.user.is_superuser:
            template = 'lims/pdf/return_labels.html'
        else:
            template = 'lims/pdf/send_labels.html'
        return template

    def get_template_context(self):
        object = self.get_object()
        context = {
            'project': object.project,
            'shipment': object,
            'admin_project': models.Project.objects.filter(is_superuser=True).first()
        }
        return context


class ShipmentEdit(OwnerRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.ShipmentForm
    template_name = "modal/form.html"
    model = models.Shipment
    success_message = "Shipment has been updated."

    def get_success_url(self):
        return reverse_lazy('shipment-detail', kwargs={'pk': self.object.pk})

    def get_initial(self):
        initial = super(ShipmentEdit, self).get_initial()
        initial.update(project=self.request.user)
        return initial


class ShipmentRevise(AdminRequiredMixin, ShipmentDetail):
    template_name = 'lims/entries/shipment-edit.html'

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.status != obj.STATES.ON_SITE:
            return HttpResponseNotAllowed
        return super().dispatch(request, *args, **kwargs)


class ShipmentComments(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.ShipmentCommentsForm
    template_name = "modal/form.html"
    model = models.Shipment
    success_message = "Shipment has been edited by staff."

    def get_success_url(self):
        return self.object.get_absolute_url()

    def form_valid(self, form):
        obj = form.instance
        if form.data.get('submit') == 'Recall':
            obj.unreceive()
            message = "Shipment un-received by staff"
            models.ActivityLog.objects.log_activity(self.request, obj, models.ActivityLog.TYPE.MODIFY, message)
        return super(ShipmentComments, self).form_valid(form)


class ShipmentDelete(OwnerRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.DeleteView):
    template_name = "modal/delete.html"
    model = models.Shipment
    success_message = "Shipment has been deleted."
    success_url = reverse_lazy('dashboard')

    def delete(self, request, *args, **kwargs):
        super(ShipmentDelete, self).delete(request, *args, **kwargs)
        success_url = self.get_success_url()
        models.ActivityLog.objects.log_activity(self.request, self.object, models.ActivityLog.TYPE.DELETE,
                                                self.success_message)
        return JsonResponse({'url': success_url})


class SendShipment(ShipmentEdit):
    form_class = forms.ShipmentSendForm

    def get_initial(self):
        initial = super(SendShipment, self).get_initial()
        initial['components'] = models.ComponentType.objects.filter(
            pk__in=self.object.components.values_list('kind__pk'))
        return initial

    def form_valid(self, form):
        components = form.cleaned_data.get('components', [])
        models.Component.objects.filter(
            pk__in=self.object.components.exclude(kind__in=components).values_list('pk')).delete()
        for component in components.exclude(pk__in=self.object.components.values_list('kind__pk')):
            models.Component.objects.create(shipment=self.object, kind=component)

        form.instance.send()
        message = "Shipment sent"
        models.ActivityLog.objects.log_activity(self.request, self.object, models.ActivityLog.TYPE.MODIFY, message)
        return super().form_valid(form)


class ReturnShipment(ShipmentEdit):
    form_class = forms.ShipmentReturnForm
    success_url = reverse_lazy('dashboard')

    def get_success_url(self):
        return self.success_url

    def form_valid(self, form):
        obj = form.instance.returned()
        message = "Shipment returned"
        models.ActivityLog.objects.log_activity(self.request, obj, models.ActivityLog.TYPE.MODIFY, message)
        return super(ReturnShipment, self).form_valid(form)


class RecallSendShipment(ShipmentEdit):
    form_class = forms.ShipmentRecallSendForm

    def get_initial(self):
        initial = super(RecallSendShipment, self).get_initial()
        initial['components'] = models.ComponentType.objects.filter(
            pk__in=self.object.components.values_list('kind__pk'))
        return initial

    def form_valid(self, form):
        components = form.cleaned_data.get('components', [])
        models.Component.objects.filter(
            pk__in=self.object.components.exclude(kind__in=components).values_list('pk')).delete()
        for component in components.exclude(pk__in=self.object.components.values_list('kind__pk')):
            models.Component.objects.create(shipment=self.object, kind=component)

        obj = form.instance
        if form.data.get('submit') == 'Recall':
            obj.unsend()
            message = "Shipping recalled"
            models.ActivityLog.objects.log_activity(self.request, obj, models.ActivityLog.TYPE.MODIFY, message)
        return super(RecallSendShipment, self).form_valid(form)


class RecallReturnShipment(ShipmentEdit):
    form_class = forms.ShipmentRecallReturnForm

    def form_valid(self, form):
        obj = form.instance
        if form.data.get('submit') == 'Recall':
            obj.unreturn()
            message = "Shipping recalled by staff"
            models.ActivityLog.objects.log_activity(self.request, obj, models.ActivityLog.TYPE.MODIFY, message)
        return super(RecallReturnShipment, self).form_valid(form)


class ArchiveShipment(ShipmentEdit):
    form_class = forms.ShipmentArchiveForm

    def form_valid(self, form):
        obj = form.instance
        obj.archive()


class ReceiveShipment(ShipmentEdit):
    form_class = forms.ShipmentReceiveForm

    def form_valid(self, form):
        obj = form.instance
        obj.receive()
        message = "Shipment received on-site"
        models.ActivityLog.objects.log_activity(self.request, obj, models.ActivityLog.TYPE.MODIFY, message)
        return super(ReceiveShipment, self).form_valid(form)


class RequestTypeList(AdminRequiredMixin, ListViewMixin, ItemListView):
    model = models.RequestType
    template_name = "lims/requesttype-list.html"
    list_columns = ['id', 'name', 'description']
    list_search = ['name', 'spec', 'description']
    link_field = 'name'
    link_url = 'requesttype-detail'
    ordering = ['name']
    ordering_proxies = {}
    list_transforms = {}
    show_project = False


class RequestTypeDetail(AdminRequiredMixin, detail.DetailView):
    model = models.RequestType
    template_name = "lims/entries/requesttype.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = forms.RequestParameterForm(kind=self.object.pk)
        return ctx


class RequestTypeCreate(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.CreateView):
    form_class = forms.RequestTypeForm
    template_name = "lims/forms/request-wizard.html"
    model = models.RequestType
    success_url = reverse_lazy('requesttype-list')
    success_message = "Request Type has been created."


class RequestTypeEdit(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.RequestTypeForm
    template_name = "lims/forms/request-wizard.html"
    model = models.RequestType
    success_message = "Request Type has been updated."

    def get_success_url(self):
        return reverse_lazy('requesttype-detail', kwargs={'pk': self.object.pk})


class RequestTypeLayout(RequestTypeEdit):
    form_class = forms.RequestTypeLayoutForm
    template_name = "lims/forms/add-wizard.html"



class RequestTypeView(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.RequestParameterForm
    template_name = "modal/form.html"
    model = models.Request
    success_message = "Request has been updated."
    success_url = reverse_lazy('request-list')

    def get_success_url(self):
        return reverse_lazy('shipment-detail', kwargs={'pk': self.object.shipment().pk})


class SampleList(ListViewMixin, ItemListView):
    model = models.Sample
    list_filters = ['modified']
    list_columns = ['id', 'name', 'comments', 'container', 'location']
    list_search = ['project__name', 'name', 'barcode', 'comments']
    link_url = 'sample-detail'
    ordering = ['-created', '-priority']
    ordering_proxies = {}
    list_transforms = {}
    plot_url = reverse_lazy("sample-stats")


class SampleStats(AdminRequiredMixin, PlotViewMixin, SampleList):
    plot_fields = {'container__kind__name': {}, }
    date_field = 'created'
    list_url = reverse_lazy("sample-list")


class SampleDetail(OwnerRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    model = models.Sample
    form_class = forms.SampleForm
    template_name = "lims/entries/sample.html"
    success_url = reverse_lazy('sample-list')
    success_message = "Sample has been updated"


class SampleEdit(OwnerRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.SampleForm
    template_name = "modal/form.html"
    model = models.Sample
    success_url = reverse_lazy('sample-list')
    success_message = "Sample has been updated."

    def get_success_url(self):
        return ""


class SampleDelete(OwnerRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.DeleteView):
    success_url = reverse_lazy('dashboard')
    template_name = "modal/delete.html"
    model = models.Sample
    success_message = "Sample has been deleted."

    def delete(self, request, *args, **kwargs):
        super(SampleDelete, self).delete(request, *args, **kwargs)
        models.ActivityLog.objects.log_activity(self.request, self.object, models.ActivityLog.TYPE.DELETE,
                                                self.success_message)
        return JsonResponse({'url': self.success_url})

    def get_context_data(self, **kwargs):
        context = super(SampleDelete, self).get_context_data(**kwargs)
        context['form_action'] = reverse_lazy('sample-delete', kwargs={'pk': self.object.pk})
        return context


class ContainerList(ListViewMixin, ItemListView):
    model = models.Container
    list_filters = ['modified', 'kind', 'status']
    list_columns = ['name', 'id', 'shipment', 'kind', 'capacity', 'num_samples', 'status']
    list_search = ['project__name', 'name', 'comments']
    link_url = 'container-detail'
    ordering = ['-created']
    ordering_proxies = {}
    list_transforms = {}


class ContainerDetail(DetailListMixin, SampleList):
    extra_model = models.Container
    template_name = "lims/entries/container.html"
    list_columns = ['name', 'barcode', 'group', 'location', 'comments']
    link_url = 'sample-detail'
    show_project = False

    def page_title(self):
        obj = self.get_object()
        return 'Samples in {}'.format(obj.name)


class ContainerEdit(OwnerRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.ContainerForm
    template_name = "modal/form.html"
    model = models.Container
    success_message = "Container has been updated."

    def get_initial(self):
        initial = super(ContainerEdit, self).get_initial()
        initial.update(project=self.request.user)
        return initial

    def get_success_url(self):
        return self.object.get_absolute_url()


class ContainerLoad(AdminRequiredMixin, ContainerEdit):
    form_class = forms.ContainerLoadForm
    template_name = "modal/form.html"

    def get_object(self, queryset=None):
        self.root = models.Container.objects.get(pk=self.kwargs['root'])
        return super().get_object(queryset=queryset)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'form-action': self.request.path
        })
        return kwargs

    def form_valid(self, form):
        data = form.cleaned_data
        location = data.get('location')
        parent = data['parent']

        if location:
            models.LoadHistory.objects.create(child=self.object, parent=data['parent'], location=location)
        else:
            parent = None
            models.LoadHistory.objects.filter(child=self.object).active().update(end=timezone.now())

        models.Container.objects.filter(pk=self.object.pk).update(parent=parent, location=location)
        return JsonResponse(self.root.get_layout(), safe=False)


class LocationLoad(AdminRequiredMixin, ContainerEdit):
    form_class = forms.LocationLoadForm
    success_message = "Container has been loaded"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'form-action': self.request.path
        })
        return kwargs

    def get_object(self, queryset=None):
        self.root = models.Container.objects.get(pk=self.kwargs['root'])
        return super().get_object(queryset=queryset)

    def get_initial(self):
        initial = super(LocationLoad, self).get_initial()
        initial.update(location=self.object.kind.locations.get(name=self.kwargs['location']))
        return initial

    def form_valid(self, form):
        data = form.cleaned_data
        models.Container.objects.filter(pk=data['child'].pk).update(
            parent=self.object, location=data['location']
        )
        models.LoadHistory.objects.create(child=data['child'], parent=self.object, location=data['location'])
        return JsonResponse(self.root.get_layout(), safe=False)


class EmptyContainers(AdminRequiredMixin, edit.UpdateView):
    form_class = forms.EmptyContainers
    template_name = "modal/form.html"
    model = models.Project
    success_message = "Containers have been removed for {username}."
    success_url = reverse_lazy('dashboard')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'form-action': self.request.path
        })
        return kwargs

    def get_object(self, queryset=None):
        self.root = models.Container.objects.get(pk=self.kwargs['root'])
        return models.Project.objects.get(username=self.kwargs.get('username'))

    def get_initial(self):
        initial = super(EmptyContainers, self).get_initial()
        initial['parent'] = models.Container.objects.get(pk=self.kwargs.get('pk'))
        return initial

    def form_valid(self, form):
        data = form.cleaned_data
        containers = self.object.containers.filter(parent=data.get('parent'))
        models.LoadHistory.objects.filter(child__in=containers).active().update(end=timezone.now())
        containers.update(**{'location': None, 'parent': None})
        return JsonResponse(self.root.get_layout(), safe=False)


class ContainerDelete(OwnerRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.DeleteView):
    success_url = reverse_lazy('dashboard')
    template_name = "modal/delete.html"
    model = models.Container
    success_message = "Container has been deleted."

    def delete(self, request, *args, **kwargs):
        super(ContainerDelete, self).delete(request, *args, **kwargs)
        models.ActivityLog.objects.log_activity(self.request, self.object, models.ActivityLog.TYPE.DELETE,
                                                self.success_message)
        return JsonResponse({'url': self.success_url})


class GroupList(ListViewMixin, ItemListView):
    model = models.Group
    list_filters = ['modified', 'status']
    list_columns = ['id', 'name', 'num_samples', 'status']
    list_search = ['project__name', 'comments', 'name']
    link_url = 'group-detail'
    ordering = ['-modified', '-priority']
    ordering_proxies = {}
    list_transforms = {}


def movable(val, record):
    return "<span class='cursor'><i class='movable ti ti-move'></i> {}</span>".format(val or "")


class GroupDetail(DetailListMixin, SampleList):
    extra_model = models.Group
    template_name = "lims/entries/group.html"
    list_columns = ['priority', 'name', 'barcode', 'container_and_location', 'comments']
    list_transforms = {
        'priority': movable,
    }
    link_url = 'sample-detail'

    def page_title(self):
        obj = self.get_object()
        if 'project' in self.list_columns:
            self.list_columns.pop(0)
        return 'Samples in {}'.format(obj.name)

    def get_object(self):
        obj = super(GroupDetail, self).get_object()
        if obj.status != self.extra_model.STATES.DRAFT:
            self.detail_ajax = False
            self.detail_target = None
        return obj


class GroupEdit(OwnerRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.GroupForm
    template_name = "lims/forms/group-edit.html"
    model = models.Group
    success_message = "Group has been updated."
    success_url = reverse_lazy('group-list')

    def get_initial(self):
        self.original_name = self.object.name
        return super(GroupEdit, self).get_initial()

    def form_valid(self, form):
        super(GroupEdit, self).form_valid(form)
        for s in self.object.samples.all():
            if self.original_name in s.name:
                models.Sample.objects.filter(pk=s.pk).update(name=s.name.replace(self.original_name, self.object.name))
        return JsonResponse({})


class GroupDelete(OwnerRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.DeleteView):
    success_url = reverse_lazy('dashboard')
    template_name = "modal/delete.html"
    model = models.Group
    success_message = "Group has been deleted."

    def delete(self, request, *args, **kwargs):
        group = self.get_object()
        super(GroupDelete, self).delete(request, *args, **kwargs)
        models.ActivityLog.objects.log_activity(self.request, group, models.ActivityLog.TYPE.DELETE,
                                                self.success_message)
        return JsonResponse({'url': group.shipment and group.shipment.get_absolute_url() or reverse_lazy('group-list')})


class DataList(ListViewMixin, ItemListView):
    model = models.Data
    list_filters = ['modified', filters.YearFilterFactory('modified'), 'kind', 'beamline']
    list_columns = ['id', 'name', 'sample', 'frame_sets', 'session__name', 'energy', 'beamline', 'kind', 'modified']
    list_search = ['id', 'name', 'beamline__name', 'sample__name', 'frames', 'project__name', 'modified']
    link_url = 'data-detail'
    link_field = 'name'
    link_attr = 'data-link'
    ordering = ['-modified']
    list_transforms = {}
    plot_url = reverse_lazy("data-stats")

    def get_queryset(self):
        return super(DataList, self).get_queryset().defer('meta_data', 'url')


class DataStats(PlotViewMixin, DataList):
    plot_fields = { 'beam_size': {'kind': 'pie'},
                    'kind__name': {'kind': 'columnchart'},
                    'reports__score': {'kind': 'histogram', 'range': (0.01, 1)},
                    'energy': {'kind': 'histogram', 'range': (4., 18.), 'bins': 8},
                    'exposure_time': {'kind': 'histogram', 'range': (0.01, 20)},
                    'attenuation': {'kind': 'histogram'},
                    'num_frames': {'kind': 'histogram'},
                    }
    date_field = 'modified'
    list_url = reverse_lazy("data-list")

    def get_metrics(self):
        return stats.parameter_summary(**self.get_active_filters())


class UsageSummary(PlotViewMixin, DataList):
    date_field = 'modified'
    list_url = reverse_lazy("data-list")
    list_filters = ['beamline', 'kind', filters.YearFilterFactory('modified'), filters.MonthFilterFactory('modified'),
                    filters.QuarterFilterFactory('modified'), filters.TimeScaleFilterFactory()]

    def get_metrics(self):
        return stats.usage_summary(period='year', **self.get_active_filters())

    def page_title(self):
        if self.kwargs.get('year'):
            return '{} Usage Metrics'.format(self.kwargs['year'])
        else:
            return 'Usage Metrics'


class DataDetail(OwnerRequiredMixin, detail.DetailView):
    model = models.Data
    template_name = "lims/entries/data.html"

    def get_template_names(self):
        return [self.object.kind.template, self.template_name]


def format_score(val, record):
    return "{:.2f}".format(val)


class ReportList(ListViewMixin, ItemListView):
    model = models.AnalysisReport
    list_filters = ['modified', 'kind']
    list_columns = ['id', 'name', 'kind', 'score', 'modified']
    list_search = ['project__username', 'name', 'data__name']
    link_field = 'name'
    link_url = 'report-detail'
    ordering = ['-modified']
    ordering_proxies = {}
    list_transforms = {
        'score': format_score
    }

    def get_queryset(self):
        return super().get_queryset().defer('details', 'url')


class ReportDetail(OwnerRequiredMixin, detail.DetailView):
    model = models.AnalysisReport
    template_name = "lims/entries/report.html"


class ShipmentDataList(DataList):
    template_name = "lims/entries/shipment-data.html"
    lookup = 'group__shipment__pk'
    detail_model = models.Shipment

    def page_title(self):
        return 'Data in {} - {}'.format(self.object.__class__.__name__.title(), self.object)

    def get_queryset(self):
        try:
            self.object = self.detail_model.objects.get(**self.kwargs)
        except self.detail_model.DoesNotExist:
            raise Http404
        qs = super().get_queryset()
        return qs.filter(**{self.lookup: self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context_name = self.object.__class__.__name__.lower()
        context[context_name] = self.object
        return context


class ShipmentReportList(ReportList):
    template_name = "lims/entries/shipment-reports.html"
    lookup = 'data__group__shipment__pk'
    detail_model = models.Shipment

    def page_title(self):
        return 'Reports in {} - {}'.format(self.object.__class__.__name__.title(), self.object)

    def get_queryset(self):
        try:
            self.object = self.detail_model.objects.get(**self.kwargs)
        except self.detail_model.DoesNotExist:
            raise Http404
        qs = super().get_queryset()
        return qs.filter(**{self.lookup: self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context_name = self.object.__class__.__name__.lower()
        context[context_name] = self.object
        return context


class RequestList(ListViewMixin, ItemListView):
    model = models.Request
    list_filters = [
        'kind',
        'status',
        filters.YearFilterFactory('created', reverse=True),
        filters.MonthFilterFactory('created'),
        filters.QuarterFilterFactory('created'),
        'project__designation',
        'project__kind',
    ]
    list_columns = ['kind', 'created', 'num_samples', 'status']
    list_search = ['kind__name', 'kind__description', 'comments', 'parameters']
    link_field = 'kind'
    link_url = 'request-detail'
    ordering = ['-created']
    list_transforms = {}


class RequestDetail(DetailListMixin, SampleList):
    extra_model = models.Request
    template_name = "lims/entries/request.html"
    list_columns = ['priority', 'name', 'barcode', 'container_and_location', 'comments']
    list_transforms = {
        'priority': movable,
    }
    link_url = 'sample-edit'
    link_attr = 'data-form-link'
    detail_target = '#modal-target'

    def page_title(self):
        obj = self.get_object()
        if 'project' in self.list_columns:
            self.list_columns.pop(0)
        return 'Samples in {}'.format(obj.name)

    def get_object(self):
        obj = super().get_object()
        if obj.status != self.extra_model.STATES.DRAFT:
            self.detail_ajax = False
            self.detail_target = None
        return obj

    def get_detail_url(self, obj):
        if self.get_object().status == self.extra_model.STATES.DRAFT:
            return super().get_detail_url(obj)
        return reverse_lazy('sample-detail', kwargs={'pk': obj.pk})


class RequestWizardCreate(LoginRequiredMixin, SessionWizardView):
    form_list = [('start', forms.RequestForm),
                 ('parameters', forms.RequestParameterForm)]
    template_name = "lims/forms/add-request.html"

    def get_context_data(self, form, **kwargs):
        ctx = super().get_context_data(form, **kwargs)
        ctx['form_title'] = "Create a Request"
        return ctx

    def get_form_initial(self, step):
        project = self.request.user
        if step == 'start':
            return self.initial_dict.get(step, {
                'project': project,
                'groups': project.sample_groups.filter(pk__in=self.request.GET.getlist('groups')),
                'samples': project.samples.filter(pk__in=self.request.GET.getlist('samples'))
            })
        elif step == 'parameters':
            start_data = self.storage.get_step_data('start')
            if start_data:
                kind = start_data.get('start-kind')
                return self.initial_dict.get(step, {
                    'kind': kind,
                    'template': start_data.get('start-template'),
                    'request': start_data.get('start-request'),
                    'comments': start_data.get('start-comments'),
                    'name': start_data.get('start-name'),
                    'samples': project.samples.filter(pk__in=start_data.getlist('start-samples')),
                    'groups': project.sample_groups.filter(pk__in=start_data.getlist('start-groups')),
                })
        return self.initial_dict.get(step, {})

    @transaction.atomic
    def done(self, form_list, **kwargs):
        info = {}
        related = {}
        for label, form in kwargs['form_dict'].items():
            if label == 'start':
                info = form.cleaned_data
                for field in ['groups', 'samples']:
                    related[field] = info.pop(field)
                info.pop('template')
                info.update({'project': models.Project.objects.get(username=self.request.user.username),})
            elif label == 'parameters':
                request = info.pop('request')
                if not request:
                    for field in ['parameters']:
                        info[field] = form.cleaned_data.get(field)
                    request, created = models.Request.objects.get_or_create(**info)
                request.groups.add(*[g for g in related['groups']])
                request.samples.add(*[s for s in related['samples']])
        return JsonResponse({})


class RequestWizardEdit(UserPassesTestMixin, SessionWizardView):
    form_list = [('start', forms.RequestForm),
                 ('parameters', forms.RequestParameterForm)]
    template_name = "lims/forms/add-request.html"

    def test_func(self):
        try:
            return models.Request.objects.get(**self.kwargs).project.username == self.request.user.username
        except models.Request.DoesNotExist:
            return False

    def get_form_instance(self, step):
        return models.Request.objects.filter(**self.kwargs).first()

    def get_form_initial(self, step):
        if step == 'parameters':
            start_data = self.storage.get_step_data('start')
            if start_data:
                kind = start_data.get('start-kind')
                return self.initial_dict.get(step, {'kind': kind,
                                                    'template': start_data.get('start-template'),
                                                    'request': start_data.get('start-request'),
                                                    'comments': start_data.get('start-comments'),
                                                    'name': start_data.get('start-name')})
        return self.initial_dict.get(step, {})

    @transaction.atomic
    def done(self, form_list, **kwargs):
        info = {}
        related = {}
        for label, form in kwargs['form_dict'].items():
            request = form.instance
            if label == 'start':
                info = form.cleaned_data
                for field in ['groups', 'samples']:
                    related[field] = info.pop(field)
                info.pop('template')
                info.pop('request')
            elif label == 'parameters':
                for field in ['parameters']:
                    info[field] = form.cleaned_data.get(field)
                models.Request.objects.filter(pk=request.pk).update(**info)
                request.groups.remove(*[g for g in request.groups.all() if g not in related['groups']])
                request.groups.add(*[g for g in related['groups']])
                request.samples.remove(*[s for s in request.samples.all() if s not in related['groups']])
                request.samples.add(*[s for s in related['samples']])
        return JsonResponse({})


class RequestEdit(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.RequestAdminForm
    template_name = "modal/form.html"
    model = models.Request
    success_message = "Request has been updated."
    success_url = reverse_lazy('request-list')

    def get_success_url(self):
        return reverse_lazy('shipment-requests', kwargs={'pk': self.object.shipment().pk})


class RequestDelete(OwnerRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.DeleteView):
    success_url = reverse_lazy('dashboard')
    template_name = "modal/delete.html"
    model = models.Request
    success_message = "Request has been deleted."

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        super().delete(request, *args, **kwargs)
        models.ActivityLog.objects.log_activity(self.request, obj, models.ActivityLog.TYPE.DELETE,
                                                self.success_message)
        return JsonResponse({'url': obj.shipment() and obj.shipment().get_absolute_url() or reverse_lazy('request-list')})


class SessionDataList(ShipmentDataList):
    template_name = "lims/entries/session-data.html"
    lookup = 'session__pk'
    detail_model = models.Session


class SessionReportList(ShipmentReportList):
    template_name = "lims/entries/session-reports.html"
    lookup = 'data__session__pk'
    detail_model = models.Session


class ActivityLogList(ListViewMixin, ItemListView):
    model = models.ActivityLog
    list_filters = ['created', 'action_type']
    list_columns = ['created', 'action_type', 'user_description', 'ip_number', 'object_repr', 'description']
    list_search = ['description', 'ip_number', 'content_type__name', 'action_type']
    ordering = ['-created']
    ordering_proxies = {}
    list_transforms = {}
    link_url = 'activitylog-detail'
    link_attr = 'data-link'
    detail_target = '#modal-target'


def format_total_time(val, record):
    return int(val) or ""


class SessionList(ListViewMixin, ItemListView):
    model = models.Session
    list_filters = [
        'beamline',
        filters.YearFilterFactory('created', reverse=True),
        filters.MonthFilterFactory('created'),
        filters.QuarterFilterFactory('created'),
        'project__designation',
        'project__kind',
        filters.NewEntryFilterFactory(field_label="First Session")
    ]
    list_columns = ['name', 'created', 'beamline', 'total_time', 'num_datasets', 'num_reports']
    list_search = ['beamline__acronym', 'project__username', 'name']
    link_field = 'name'
    ordering = ['-created']
    list_transforms = {
        'total_time': lambda x, y: '{:0.1f} h'.format(x)
    }
    link_url = 'session-detail'


class SessionDetail(OwnerRequiredMixin, detail.DetailView):
    model = models.Session
    template_name = "lims/entries/session.html"


class SessionStatistics(AdminRequiredMixin, detail.DetailView):
    model = models.Session
    template_name = "lims/entries/session-statistics.html"
    page_title = "Session Statistics"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = stats.session_stats(self.object)
        return context


class BeamlineDetail(AdminRequiredMixin, detail.DetailView):
    model = models.Beamline
    template_name = "lims/entries/beamline.html"


class AutomounterEdit(OwnerRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.AutomounterForm
    template_name = "modal/form.html"
    model = models.Automounter
    success_url = reverse_lazy('dashboard')
    success_message = "Comments have been updated."


class ShipmentCreate(LoginRequiredMixin, SessionWizardView):
    form_list = [('shipment', forms.AddShipmentForm),
                 ('containers', forms.ShipmentContainerForm),
                 ('groups', forms.ShipmentGroupForm)]
    template_name = "modal/wizard.html"

    def get_context_data(self, form, **kwargs):
        ctx = super().get_context_data(form, **kwargs)
        ctx['form_title'] = "Create a Shipment"
        return ctx

    def get_form_initial(self, step):
        if step == 'shipment':
            today = timezone.now()
            day_count = self.request.user.shipments.filter(
                created__year=today.year, created__month=today.month, created__day=today.day
            ).count()
            return self.initial_dict.get(step, {
                'project': self.request.user,
                'name': '{} #{}'.format(timezone.now().strftime('%Y-%b%d'), day_count + 1)
            })
        elif step == 'groups':
            containers_data = self.storage.get_step_data('containers')
            if containers_data:
                names = containers_data.getlist('containers-name')
                kinds = containers_data.getlist('containers-kind')
                containers = [(names[i], kinds[i]) for i in range(len(names))]
                return self.initial_dict.get(step, {'containers': containers})
        return self.initial_dict.get(step, {})

    @transaction.atomic
    def done(self, form_list, **kwargs):
        project = None
        for label, form in kwargs['form_dict'].items():
            if label == 'shipment':
                data = form.cleaned_data
                if self.request.user.is_superuser:
                    data.update({
                        'project': data.get('project'),
                        'staff_comments': 'Created by staff!'
                    })
                else:
                    data.update({
                        'project': self.request.user
                    })
                project = data['project']
                self.shipment, created = models.Shipment.objects.get_or_create(**data)
            elif label == 'containers':
                for i, name in enumerate(form.cleaned_data['name_set']):
                    data = {
                        'kind': models.ContainerType.objects.get(pk=form.cleaned_data['kind_set'][i]),
                        'name': name.upper(),
                        'shipment': self.shipment,
                        'project': project
                    }
                    models.Container.objects.get_or_create(**data)
            elif label == 'groups':
                if self.request.POST.get('submit') == 'Fill':
                    for i, container in enumerate(self.shipment.containers.all()):
                        group = self.shipment.groups.create(name=container.name, project=project, priority=(i+1))
                        group_samples = [
                            models.Sample(
                                name='{}_{}'.format(group.name, location.name), group=group, project=project,
                                container=container, location=location
                            )
                            for location in container.kind.locations.all()
                        ]
                        models.Sample.objects.bulk_create(group_samples)
                else:
                    for i, name in enumerate(form.cleaned_data['name_set']):
                        if name:
                            data = {
                                field: form.cleaned_data['{}_set'.format(field)][i]
                                for field in ['name', 'comments']
                            }

                            data.update({
                                'shipment': self.shipment,
                                'project': project,
                                'priority': i + 1
                            })
                            models.Group.objects.get_or_create(**data)

        # Staff created shipments should be sent and received automatically.
        if self.request.user.is_superuser:
            self.shipment.send()
            self.shipment.receive()
        return JsonResponse({'url': reverse('shipment-detail', kwargs={'pk': self.shipment.pk})})


class ShipmentAddContainer(LoginRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.FormView):
    form_class = forms.ShipmentContainerForm
    template_name = "lims/forms/add-wizard.html"
    success_message = "Shipment updated"

    def get_initial(self):
        initial = super(ShipmentAddContainer, self).get_initial()
        initial['shipment'] = models.Shipment.objects.get(pk=self.kwargs.get('pk'))
        return initial

    @transaction.atomic
    def form_valid(self, form):
        data = form.cleaned_data
        data['shipment'].containers.exclude(pk__in=[int(pk) for pk in data['id_set'] if pk]).delete()
        for i, name in enumerate(data['name_set']):
            if data['id_set'][i]:
                models.Container.objects.filter(pk=int(data['id_set'][i])).update(name=data['name_set'][i])
            else:
                info = {
                    'kind': models.ContainerType.objects.get(pk=form.cleaned_data['kind_set'][i]),
                    'name': name.upper(),
                    'shipment': data['shipment'],
                    'project': data['shipment'].project,
                    'status': data['shipment'].status
                }
                models.Container.objects.get_or_create(**info)
        return HttpResponseRedirect(reverse('shipment-add-groups', kwargs={'pk': self.kwargs.get('pk')}))


class ShipmentAddGroup(LoginRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.CreateView):
    model = models.Group
    form_class = forms.ShipmentGroupForm
    template_name = "lims/forms/add-wizard.html"
    success_message = "Groups in shipment updated"

    def get_initial(self):
        initial = super(ShipmentAddGroup, self).get_initial()
        initial['shipment'] = models.Shipment.objects.get(pk=self.kwargs.get('pk'))
        initial['containers'] = [(c.pk, c.kind.pk) for c in initial['shipment'].containers.all()]
        initial['sample_locations'] = json.dumps(
            {g.name: {c.pk: list(c.samples.filter(group=g).values_list('location', flat=True))
                      for c in initial['shipment'].containers.all()}
             for g in initial['shipment'].groups.all()})
        if initial['shipment']:
            initial['containers'] = initial['shipment'].containers.all()
        return initial

    @transaction.atomic
    def form_valid(self, form):
        data = form.cleaned_data
        shipment = data['shipment']
        shipment.groups.exclude(pk__in=[int(v) for v in data['id_set'] if v]).delete()

        for i, name in enumerate(data['name_set']):
            info = {
                field: data['{}_set'.format(field)][i]
                for field in ['name', 'comments']}
            info.update({
                'shipment': data['shipment'],
                'project': data['shipment'].project,
                'priority': i + 1
            })
            if data['id_set'][i]:
                models.Group.objects.filter(pk=int(data['id_set'][i])).update(**info)
            else:
                models.Group.objects.get_or_create(**info)

        return JsonResponse({})


class SeatSamples(OwnerRequiredMixin, AsyncFormMixin, detail.DetailView):
    template_name = "lims/forms/seat-samples.html"
    model = models.Shipment


class ContainerSpreadsheet(LoginRequiredMixin, AsyncFormMixin, detail.DetailView):
    template_name = "lims/forms/container-spreadsheet.html"
    model = models.Container

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if request.user.is_superuser:
            qs = models.Container.objects.filter()
        else:
            qs = models.Container.objects.filter(project=self.request.user)
        try:
            container = qs.get(pk=self.kwargs['pk'])
            samples = json.loads(request.POST.get('samples', '[]'))
            groups = {
                sample['group'] if sample['group'] else sample['name']  # use sample name if group is blank
                for sample in samples
                if sample['name']
            }
            group_map = {}
            for name in groups:
                group, created = models.Group.objects.get_or_create(
                    project=container.project, shipment=container.shipment,
                    name=name,
                )
                group_map[name] = group

            for sample in samples:
                group_name = sample['group'] if sample['group'] else sample['name']  # use name if group is blank
                info = {
                    'name': sample['name'],
                    'group': group_map.get(group_name),
                    'location_id': sample['location'],
                    'container': container,
                    'barcode': sample['barcode'],
                    'comments': sample['comments'],
                }
                if sample.get('name') and sample.get('sample'):  # update entries
                    models.Sample.objects.filter(project=container.project, pk=sample.get('sample')).update(**info)
                elif sample.get('name'):  # create new entry
                    models.Sample.objects.create(project=container.project, **info)
                else:  # delete existing entry
                    models.Sample.objects.filter(
                        project=container.project, location_id=sample['location'], container=container
                    ).delete()

            return JsonResponse({'url': container.get_absolute_url()}, safe=False)
        except models.Container.DoesNotExist:
            raise http.Http404('Container Not Found!')


class SSHKeyCreate(UserPassesTestMixin, SuccessMessageMixin, AsyncFormMixin, edit.CreateView):
    form_class = forms.SSHKeyForm
    template_name = "modal/form.html"
    model = models.SSHKey
    success_url = reverse_lazy('dashboard')
    success_message = "SSH key has been created"

    def test_func(self):
        # Allow access to admin or owner
        return self.request.user.is_superuser or self.kwargs['username'] == self.request.user.username

    def get_success_url(self):
        return reverse_lazy('project-profile', kwargs={'username': self.kwargs['username']})

    def get_initial(self):
        initial = super().get_initial()
        try:
            initial['project'] = models.Project.objects.get(username=self.kwargs['username'])
        except models.Project.DoesNotExist:
            return http.Http404

        return initial


class SSHKeyEdit(LoginRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.SSHKeyForm
    template_name = "modal/form.html"
    model = models.SSHKey
    success_url = reverse_lazy('dashboard')
    success_message = "SSH key has been updated"


class SSHKeyDelete(LoginRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.DeleteView):
    template_name = "modal/delete.html"
    model = models.SSHKey
    success_url = reverse_lazy('dashboard')
    success_message = "SSH key has been deleted"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_action'] = reverse_lazy('sshkey-delete', kwargs={'pk': self.object.pk})
        return context


class GuideView(detail.DetailView):
    model = models.Guide
    template_name = "lims/components/guide-youtube.html"

    def get_object(self, queryset=None):
        if self.request.user.is_superuser:
            return super().get_object(queryset=queryset)
        else:
            return super().get_object(queryset=self.get_queryset().filter(staff_only=False))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.object.title
        context.update(self.kwargs)
        return context


class GuideCreate(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.CreateView):
    form_class = forms.GuideForm
    template_name = "modal/form.html"
    model = models.Guide
    success_url = reverse_lazy('dashboard')
    success_message = "Guide has been created"


class GuideEdit(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.GuideForm
    template_name = "modal/form.html"
    model = models.Guide
    success_url = reverse_lazy('dashboard')
    success_message = "Guide has been updated"


class GuideDelete(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.DeleteView):
    template_name = "modal/delete.html"
    model = models.Guide
    success_url = reverse_lazy('dashboard')
    success_message = "Guide has been deleted"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_action'] = reverse_lazy('guide-delete', kwargs={'pk': self.object.pk})
        return context


class ProxyView(View):
    def get(self, request, *args, **kwargs):
        remote_url = DOWNLOAD_PROXY_URL + request.path
        if kwargs.get('section') == 'archive':
            return fetch_archive(request, remote_url)
        return proxy_view(request, remote_url)


def fetch_archive(request, url):
    r = requests.get(url, stream=True)
    if r.status_code == 200:
        resp = http.StreamingHttpResponse(r, content_type='application/x-gzip')
        resp['Content-Disposition'] = r.headers.get('Content-Disposition', 'attachment; filename=archive.tar.gz')
        return resp
    else:
        return http.HttpResponseNotFound()


class ProjectList(AdminRequiredMixin, ItemListView):
    model = models.Project
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
    model = models.Project
    template_name = "lims/entries/user-info.html"

    def get_object(self, **kwargs):
        return models.Project.objects.get(username=self.kwargs.get('username'))


class UserStats(UserDetail):
    template_name = "lims/entries/user.html"
    page_title = "User Profile"

    def get_object(self, **kwargs):
        return models.Project.objects.get(username=self.kwargs.get('username'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = stats.project_stats(self.object)
        return context


class ProjectCreate(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.CreateView):
    form_class = forms.NewProjectForm
    template_name = "modal/form.html"
    model = models.Project
    success_url = reverse_lazy('user-list')
    success_message = "New Account '%(username)s' has been created."

    def form_valid(self, form):
        # create local user
        response = super().form_valid(form)
        info_msg = 'New Account {} added'.format(self.object)

        models.ActivityLog.objects.log_activity(
            self.request, self.object, models.ActivityLog.TYPE.CREATE, info_msg
        )
        # messages are simply passed down to the template via the request context
        return response


class ProjectDelete(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.DeleteView):
    template_name = "modal/delete.html"
    model = models.Project
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
        self.success_message = "{} account has been deleted".format(kwargs.get('username'))
        return JsonResponse({'url': self.success_url}, safe=False)


def record_logout(sender, user, request, **kwargs):
    """ user logged outof the system """
    models.ActivityLog.objects.log_activity(request, user, models.ActivityLog.TYPE.LOGOUT, '{} logged-out'.format(user.username))


def record_login(sender, user, request, **kwargs):
    """ Login a user into the system """
    if user.is_authenticated:
        models.ActivityLog.objects.log_activity(request, user, models.ActivityLog.TYPE.LOGIN, '{} logged-in'.format(user.username))
        last_login = models.ActivityLog.objects.last_login(request)
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
