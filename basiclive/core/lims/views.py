import json
import uuid
from typing import Any

import httpx2
from crisp_modals.views import ModalCreateView, ModalUpdateView, ModalDeleteView, ModalFormView
from django import http
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils import dateformat, timezone
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import edit, detail, View
from formtools.wizard.views import SessionWizardView
from itemlist.views import ItemListView

from basiclive.core.lims.conf import settings
from basiclive.utils import filters
from basiclive.utils.mixins import AdminRequiredMixin, PlotViewMixin, AuthenticationRequiredMixin
from . import forms, models, stats
from .icons import render_icon
from ...utils.reporting import translate_report

if settings.USE_SCHEDULE:
    from basiclive.core.schedule.models import BeamlineSupport


class OwnerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Mixin to limit access to the owner of an object (or superusers).
    Must be used with an object-based View (e.g. DetailView, EditView)
    """
    owner_field = 'project'

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        obj = self.get_object()
        target = getattr(obj, self.owner_field, None) if self.owner_field else obj
        if target is None and isinstance(obj, models.Project):
            target = obj
        if isinstance(target, models.Project):
            return self.request.user.can_access_project(target)
        return target == self.request.user


class ProjectEdit(UserPassesTestMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.ProjectForm
    model = models.Project
    success_message = "Profile has been updated."

    def get_object(self, queryset=None):
        code = self.kwargs.get('code') or self.kwargs.get('username') or self.kwargs.get('name')
        return models.Project.objects.filter(
            models.Q(code=code)
        ).first() or models.Project.objects.get(code=code)

    def test_func(self):
        """Allow access to admin or project members"""
        try:
            return self.request.user.can_access_project(self.get_object())
        except models.Project.DoesNotExist:
            return False

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        kwarg_val = self.kwargs.get('code') or self.kwargs.get('name') or self.kwargs.get('username')
        return reverse_lazy('project-profile', kwargs={'code': kwarg_val})


class ProjectLabels(AdminRequiredMixin, detail.DetailView):
    template_name = "lims/pdf/return-labels.html"
    model = models.Project
    slug_field = 'code'
    slug_url_kwarg = 'code'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sender = self.request.user
        if settings.USE_SCHEDULE:
            support = BeamlineSupport.objects.filter(date=timezone.localtime().date()).first()
            if support:
                sender = support.staff
        context.update({
            'project': self.get_object(),
            'shipment': None,
            'system': models.SystemSettings.load(),
            'sender': sender
        })
        return context


class ListViewMixin(LoginRequiredMixin):
    paginate_by = 16
    template_name = "lims/list.html"
    link_data = False
    show_project = True

    def get_list_columns(self):
        columns = super().get_list_columns()
        if self.request.user.is_superuser and self.show_project:
            return ['project__code'] + columns
        return columns

    def get_queryset(self):
        selector = {}
        if not self.request.user.is_superuser:
            if not self.request.project:
                return super().get_queryset().none()
            selector = {'project': self.request.project}
        return super().get_queryset().filter(**selector)

    def page_title(self):
        return self.model._meta.verbose_name_plural.title()


class DetailListMixin(OwnerRequiredMixin):
    extra_model = None
    add_url = None
    list_filters = []
    paginate_by = 16

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
    list_filters = [filters.YearFilter('created'), 'status']
    list_columns = ['id', 'name', 'date_shipped', 'carrier', 'num_containers', 'status']
    list_search = ['project__code', 'name', 'comments', 'status']
    link_url = 'shipment-detail'
    link_data = False
    ordering = ['status', '-modified']

    def get_queryset(self):
        if self.request.user.is_superuser:
            return super(ShipmentList, self).get_queryset().filter(
                status__gte=models.Shipment.STATES.SENT)
        return super(ShipmentList, self).get_queryset()


class ShipmentDetail(OwnerRequiredMixin, detail.DetailView):
    model = models.Shipment
    template_name = "lims/details/shipment.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['automounters'] = {
            container.pk: container.automounter() for container in self.object.containers.all()
        }
        return ctx


class ShipmentLabels(OwnerRequiredMixin, detail.DetailView):
    model = models.Shipment
    template_name = "lims/pdf/return-labels.html"

    def get_template_name(self):
        if self.request.user.is_superuser:
            template = 'lims/pdf/return-labels.html'
        else:
            template = 'lims/pdf/send-labels.html'
        return template

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        shipment = self.get_object()
        context.update({
            'project': shipment.project,
            'shipment': shipment,
            'system': models.SystemSettings.load(),
            'sender': shipment.project.pi
        })
        return context


class ShipmentEdit(OwnerRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.ShipmentForm
    model = models.Shipment
    success_message = "Shipment has been updated."

    def get_initial(self):
        initial = super(ShipmentEdit, self).get_initial()
        initial.update(project=self.request.project)
        return initial


class ShipmentComments(AdminRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.ShipmentCommentsForm
    model = models.Shipment
    success_message = "Shipment has been edited by staff."

    def form_valid(self, form):
        obj = form.instance
        if form.data.get('submit') == 'Recall':
            obj.unreceive()
            message = "Shipment recalled by staff"
            models.ActivityLog.objects.log_activity(self.request, obj, models.ActivityLog.TYPE.MODIFY, message)
        return super(ShipmentComments, self).form_valid(form)


class ShipmentDelete(OwnerRequiredMixin, SuccessMessageMixin, ModalDeleteView):
    model = models.Shipment
    success_message = "Shipment has been deleted."
    success_url = reverse_lazy('shipment-list')

    def confirmed(self, *args, **kwargs):
        response = super().confirmed(*args, **kwargs)
        message = f"Shipment {self.object} deleted."
        models.ActivityLog.objects.log_activity(
            self.request, self.object, models.ActivityLog.TYPE.DELETE,
            message
        )
        return response


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
        message = f"Shipment {self.object} sent"
        models.ActivityLog.objects.log_activity(self.request, self.object, models.ActivityLog.TYPE.MODIFY, message)
        return super().form_valid(form)


class ReturnShipment(ShipmentEdit):
    form_class = forms.ShipmentReturnForm

    def form_valid(self, form):
        obj = form.instance.returned()
        message = f"Shipment {self.object} returned"
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
            message = f"Shipping {obj} recalled"
            models.ActivityLog.objects.log_activity(self.request, obj, models.ActivityLog.TYPE.MODIFY, message)
        return super(RecallSendShipment, self).form_valid(form)


class RecallReturnShipment(ShipmentEdit):
    form_class = forms.ShipmentRecallReturnForm

    def form_valid(self, form):
        obj = form.instance
        if form.data.get('submit') == 'Recall':
            obj.unreturn()
            message = f"Shipping {obj} recalled by staff"
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
        message = f"Shipment {obj} received on-site"
        models.ActivityLog.objects.log_activity(self.request, obj, models.ActivityLog.TYPE.MODIFY, message)
        return super(ReceiveShipment, self).form_valid(form)


class RequestTypeList(AdminRequiredMixin, ListViewMixin, ItemListView):
    model = models.RequestType
    template_name = "lims/details/request-type-list.html"
    list_columns = ['id', 'name', 'description']
    list_search = ['name', 'spec', 'description']
    link_field = 'name'
    link_url = 'request-type-detail'
    ordering_proxies = {}
    list_transforms = {}
    show_project = False


class RequestTypeDetail(AdminRequiredMixin, detail.DetailView):
    model = models.RequestType
    template_name = "lims/details/request-type.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = forms.RequestParameterForm(kind=self.object.pk)
        return ctx


class RequestTypeCreate(AdminRequiredMixin, SuccessMessageMixin, ModalCreateView):
    form_class = forms.RequestTypeForm
    template_name = "lims/forms/request-wizard.html"
    model = models.RequestType
    success_message = "Request Type has been created."


class RequestTypeEdit(AdminRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.RequestTypeForm
    template_name = "lims/forms/request-wizard.html"
    model = models.RequestType
    success_message = "Request Type has been updated."


class RequestTypeLayout(RequestTypeEdit):
    form_class = forms.RequestTypeLayoutForm
    template_name = "lims/forms/add-wizard.html"


class SampleList(ListViewMixin, ItemListView):
    model = models.Sample
    list_filters = ['modified']
    list_columns = ['id', 'name', 'comments', 'container', 'location']
    list_search = ['project__code', 'name', 'barcode', 'comments']
    link_url = 'sample-detail'
    ordering = ['-created', '-priority']
    ordering_proxies = {}
    list_transforms = {}
    plot_url = reverse_lazy("sample-stats")


class SampleStats(AdminRequiredMixin, PlotViewMixin, SampleList):
    plot_fields = {'container__kind__name': {}, }
    date_field = 'created'
    list_url = reverse_lazy("sample-list")


class SampleDetail(OwnerRequiredMixin, SuccessMessageMixin, detail.DetailView):
    model = models.Sample
    template_name = "lims/details/sample.html"


class SampleEdit(OwnerRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.SampleForm
    model = models.Sample
    success_message = "Sample has been updated."


class SampleDelete(OwnerRequiredMixin, SuccessMessageMixin, ModalDeleteView):
    success_url = reverse_lazy('sample-list')
    model = models.Sample
    success_message = "Sample has been deleted."

    def confirmed(self, *args, **kwargs):
        response = super().confirmed(*args, **kwargs)
        message = f"Sample {self.object} deleted"
        models.ActivityLog.objects.log_activity(
            self.request, self.object, models.ActivityLog.TYPE.DELETE, message
        )
        return response

    def get_context_data(self, **kwargs):
        context = super(SampleDelete, self).get_context_data(**kwargs)
        context['form_action'] = reverse_lazy('sample-delete', kwargs={'pk': self.object.pk})
        return context


class ContainerList(ListViewMixin, ItemListView):
    model = models.Container
    list_filters = ['modified', 'kind', 'status']
    list_columns = ['name', 'id', 'shipment', 'kind', 'capacity', 'num_samples', 'status']
    list_search = ['project__code', 'name', 'comments']
    link_url = 'container-detail'
    ordering = ['-created']
    ordering_proxies = {}
    list_transforms = {}
    paginate_by = 16


class ContainerDetail(DetailListMixin, SampleList):
    extra_model = models.Container
    template_name = "lims/details/container.html"
    list_columns = ['name', 'barcode', 'group', 'location', 'comments']
    link_url = 'sample-detail'
    show_project = False

    def page_title(self):
        obj = self.get_object()
        return 'Samples in {}'.format(obj.name)


class ContainerEdit(OwnerRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.ContainerForm
    model = models.Container
    success_message = "Container has been updated."

    def get_initial(self):
        initial = super(ContainerEdit, self).get_initial()
        initial.update(project=self.request.project)
        return initial

    def get_success_url(self):
        return self.object.get_absolute_url()


class ContainerLoad(AdminRequiredMixin, ContainerEdit):
    form_class = forms.ContainerLoadForm

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
    model = models.Project
    success_message = "Containers have been removed for {name}."
    success_url = reverse_lazy('container-list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'form-action': self.request.path
        })
        return kwargs

    def get_object(self, queryset=None):
        self.root = models.Container.objects.get(pk=self.kwargs['root'])
        proj_ident = self.kwargs.get('project')
        return models.Project.objects.filter(models.Q(code=proj_ident) | models.Q(id=int(proj_ident) if str(proj_ident).isdigit() else -1)).first() or models.Project.objects.get(code=proj_ident)

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


class ContainerDelete(OwnerRequiredMixin, SuccessMessageMixin, ModalDeleteView):
    success_url = reverse_lazy('container-list')
    model = models.Container
    success_message = "Container has been deleted."

    def confirmed(self, *args, **kwargs):
        response = super().confirmed(*args, **kwargs)
        message = f"Container {self.object} deleted"
        models.ActivityLog.objects.log_activity(
            self.request, self.object, models.ActivityLog.TYPE.DELETE, message
        )
        return response


class GroupList(ListViewMixin, ItemListView):
    model = models.Group
    list_filters = ['modified', 'status']
    list_columns = ['id', 'name', 'num_samples', 'status']
    list_search = ['project__code', 'comments', 'name']
    link_url = 'group-detail'
    ordering = ['-modified', '-priority']
    ordering_proxies = {}
    list_transforms = {}


def movable(val, record):
    return f"<span class='cursor'>{render_icon('move', extra_class='movable')} {val or ''}</span>"


class GroupDetail(DetailListMixin, SampleList):
    extra_model = models.Group
    template_name = "lims/details/group.html"
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


class GroupEdit(OwnerRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.GroupForm
    template_name = "lims/forms/group-edit.html"
    model = models.Group
    success_message = "Group has been updated."
    success_url = reverse_lazy('group-list')

    def get_initial(self):
        self.original_name = self.object.name
        return super(GroupEdit, self).get_initial()

    def form_valid(self, form):
        response = super(GroupEdit, self).form_valid(form)
        for s in self.object.samples.all():
            if self.original_name in s.name:
                models.Sample.objects.filter(pk=s.pk).update(name=s.name.replace(self.original_name, self.object.name))
        return response


class GroupDelete(OwnerRequiredMixin, SuccessMessageMixin, ModalDeleteView):
    success_url = reverse_lazy('group-list')
    model = models.Group
    success_message = "Group has been deleted."

    def get_success_url(self):
        return self.object.shipment and self.object.shipment.get_absolute_url() or reverse_lazy('group-list')

    def confirmed(self, *args, **kwargs):
        response = super().confirmed(*args, **kwargs)
        message = f"Group {self.object} deleted"
        models.ActivityLog.objects.log_activity(
            self.request, self.object, models.ActivityLog.TYPE.DELETE, message
        )
        return response


class DataList(ListViewMixin, ItemListView):
    model = models.Data
    list_filters = [
        'modified',
        filters.YearFilter('modified'),
        'kind',
        'beamline'
    ]
    list_columns = ['id', 'name', 'sample', 'frame_sets', 'session__name', 'energy', 'beamline', 'kind', 'modified']
    list_search = ['id', 'name', 'beamline__name', 'sample__name', 'frames', 'project__code', 'modified']
    link_url = 'data-detail'
    link_field = 'name'
    link_attr = 'data-modal-url'
    ordering = ['-modified']
    list_transforms = {}
    plot_url = reverse_lazy("data-stats")


class DataDetail(OwnerRequiredMixin, detail.DetailView):
    model = models.Data
    template_name = "lims/data/data.html"

    def get_template_names(self):
        return [self.object.kind.template, self.template_name]


def format_score(val, record):
    return f"{val:.2f}"


class ReportList(ListViewMixin, ItemListView):
    model = models.AnalysisReport
    list_filters = ['modified', 'kind']
    list_columns = ['id', 'name', 'kind', 'score', 'modified']
    list_search = ['project__code', 'name', 'data__name']
    link_field = 'name'
    link_url = 'report-detail'
    ordering = ['-modified']
    ordering_proxies = {}
    list_transforms = {
        'score': format_score
    }


class ReportDetail(OwnerRequiredMixin, detail.DetailView):
    model = models.AnalysisReport
    template_name = "lims/details/report.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        if isinstance(self.object.details, list) and self.object.details:
            report_data = translate_report(self.object.details)
        else:
            report_data = self.object.details
        context['report_data'] = report_data
        return context


class ShipmentDataList(DataList):
    template_name = "lims/details/shipment-data.html"
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
    template_name = "lims/details/shipment-reports.html"
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
        filters.YearFilter('created', reverse=True),
        filters.MonthFilter('created'),
        filters.QuarterFilter('created'),
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
    template_name = "lims/details/request.html"
    list_columns = ['priority', 'name', 'barcode', 'container_and_location', 'comments']
    list_transforms = {
        'priority': movable,
    }
    link_url = 'sample-edit'
    link_attr = 'data-modal-url'
    detail_target = '#modal-target'

    def page_title(self):
        obj = self.get_object()
        if 'project' in self.list_columns:
            self.list_columns.pop(0)
        return f'Samples in {obj.name}'

    def get_object(self):
        obj = super().get_object()
        if obj.status != self.extra_model.STATES.DRAFT:
            self.detail_target = None
        return obj

    def get_detail_url(self, obj):
        if self.get_object().status == self.extra_model.STATES.DRAFT:
            return super().get_detail_url(obj)
        return reverse_lazy('sample-detail', kwargs={'pk': obj.pk})


class RequestWizardCreate(LoginRequiredMixin, SessionWizardView):
    form_list = [
        ('start', forms.RequestForm),
        ('parameters', forms.RequestParameterForm)
    ]
    template_name = "lims/forms/add-request.html"

    def get_context_data(self, form, **kwargs):
        ctx = super().get_context_data(form, **kwargs)
        ctx['form_title'] = "Create a Request"
        return ctx

    def get_form_initial(self, step):
        project = self.request.project
        group_ids = list(self.request.GET.getlist('groups'))
        sample_ids = list(self.request.GET.getlist('samples'))
        extras = {'groups': [], 'samples': [], 'name': ''}
        if project:
            if 'group' in self.kwargs or group_ids:
                group_ids = [self.kwargs.get('group')] if self.kwargs.get('group') else group_ids
                groups = project.sample_groups.filter(pk__in=group_ids)
                names = '/'.join(groups.values_list('name', flat=True))
                extras['groups'] = groups
                extras['name'] = f'{names} - '

            if 'sample' in self.kwargs or sample_ids:
                sample_ids = [self.kwargs.get('sample')] if self.kwargs.get('sample') else sample_ids
                samples = project.samples.filter(pk__in=sample_ids)
                names = '/'.join(samples.values_list('name', flat=True))
                extras['samples'] = samples
                extras['name'] = f'{names} - '

        if step == 'start':
            return self.initial_dict.get(step, {
                'project': project,
                **extras
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
                    'samples': project.samples.filter(pk__in=start_data.getlist('start-samples')) if project else models.Sample.objects.none(),
                    'groups': project.sample_groups.filter(pk__in=start_data.getlist('start-groups')) if project else models.SampleGroup.objects.none(),
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
                info.update({'project': self.request.project})
            elif label == 'parameters':
                request = info.pop('request', None)
                if not request:
                    for field in ['parameters']:
                        info[field] = form.cleaned_data.get(field)
                    request, created = models.Request.objects.get_or_create(**info)
                request.groups.add(*[g for g in related['groups']])
                request.samples.add(*[s for s in related['samples']])
        return JsonResponse({})


class RequestWizardEdit(UserPassesTestMixin, SessionWizardView):
    form_list = [
        ('start', forms.RequestForm),
        ('parameters', forms.RequestParameterForm)
    ]
    template_name = "lims/forms/add-request.html"

    def test_func(self):
        try:
            req = models.Request.objects.get(**self.kwargs)
            return self.request.user.can_access_project(req.project)
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
            elif label == 'parameters':
                for field in ['parameters']:
                    info[field] = form.cleaned_data.get(field)
                models.Request.objects.filter(pk=request.pk).update(**info)
                request.groups.remove(*[g for g in request.groups.all() if g not in related['groups']])
                request.groups.add(*[g for g in related['groups']])
                request.samples.remove(*[s for s in request.samples.all() if s not in related['groups']])
                request.samples.add(*[s for s in related['samples']])
        return JsonResponse({})


class RequestEdit(AdminRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.RequestAdminForm
    model = models.Request
    success_message = "Request has been updated."
    success_url = reverse_lazy('request-list')

    def get_success_url(self):
        return reverse_lazy('shipment-requests', kwargs={'pk': self.object.shipment().pk})


class RequestDelete(OwnerRequiredMixin, SuccessMessageMixin, ModalDeleteView):
    success_url = reverse_lazy('request-list')
    model = models.Request
    success_message = "Request has been deleted."

    def get_success_url(self):
        return self.object.shipment() and self.object.shipment().get_absolute_url() or reverse_lazy('request-list')

    def confirmed(self, *args, **kwargs):
        response = super().confirmed(*args, **kwargs)
        models.ActivityLog.objects.log_activity(
            self.request, self.object, models.ActivityLog.TYPE.DELETE, f"Request {self.object} deleted"
        )
        return response


class SessionDataList(ShipmentDataList):
    template_name = "lims/details/session-data.html"
    lookup = 'session__pk'
    detail_model = models.Session


class SessionReportList(ShipmentReportList):
    template_name = "lims/details/session-reports.html"
    lookup = 'data__session__pk'
    detail_model = models.Session


class ActivityLogList(ListViewMixin, ItemListView):
    model = models.ActivityLog
    list_filters = ['created', 'action_type']
    list_columns = ['created', 'action_type', 'user', 'ip_number', 'object_repr', 'description']
    list_search = ['description', 'ip_number', 'content_type__name', 'action_type']
    ordering = ['-created']
    ordering_proxies = {}
    list_transforms = {}


def format_total_time(val, record):
    return int(val) or ""


class SessionList(ListViewMixin, ItemListView):
    model = models.Session
    list_filters = [
        'beamline',
        filters.YearFilter('created', reverse=True),
        filters.MonthFilter('created'),
        filters.QuarterFilter('created'),
        'project__designation',
        'project__kind',
        filters.NewEntryFilter(field_label="First Session")
    ]
    list_columns = ['name', 'created', 'beamline', 'total_time', 'num_datasets', 'num_reports']
    list_search = ['beamline__acronym', 'project__code', 'name']
    link_field = 'name'
    ordering = ['-created']
    list_transforms = {
        'total_time': lambda x, y: '{:0.1f} h'.format(x)
    }
    link_url = 'session-detail'


class SessionDetail(OwnerRequiredMixin, detail.DetailView):
    model = models.Session
    template_name = "lims/details/session.html"


class SessionStatistics(AdminRequiredMixin, detail.DetailView):
    model = models.Session
    template_name = "lims/details/session-statistics.html"
    page_title = "Session Statistics"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = stats.session_stats(self.object)
        return context


class BeamlineDetail(AdminRequiredMixin, detail.DetailView):
    model = models.Beamline
    template_name = "lims/details/beamline.html"


class AutomounterEdit(OwnerRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.AutomounterForm
    model = models.Automounter
    success_url = '/'
    success_message = "Comments have been updated."


class ShipmentCreate(LoginRequiredMixin, SessionWizardView):
    form_list = [
        ('shipment', forms.AddShipmentForm),
        ('containers', forms.ShipmentContainerForm),
        ('groups', forms.ShipmentGroupForm)
    ]
    template_name = "lims/modal/wizard.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_superuser:
            project = getattr(request, 'project', None)
            if not project or project.is_expired:
                raise PermissionDenied("Cannot create a shipment for an expired project.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, form, **kwargs):
        ctx = super().get_context_data(form, **kwargs)
        ctx['form_title'] = "Create a Shipment"
        return ctx

    def get_form_kwargs(self, step=None):
        kwargs = super().get_form_kwargs(step)
        if step == 'shipment':
            kwargs.update({'user': self.request.user})
        return kwargs

    def get_form_initial(self, step):
        if step == 'shipment':
            today = timezone.now()
            project = self.request.project
            day_count = project.shipments.filter(
                created__year=today.year, created__month=today.month, created__day=today.day
            ).count() if project else 0
            return self.initial_dict.get(step, {
                'project': project,
                'name': f'{timezone.now().strftime("%Y-%b%d")} #{day_count + 1}'
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
                        'project': self.request.project
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

        # Staff created shipments for other projects should be sent and received automatically
        if self.request.user.is_superuser and (not self.request.project or self.shipment.project != self.request.project):
            self.shipment.send()
            self.shipment.receive()
        return JsonResponse({'url': reverse('shipment-detail', kwargs={'pk': self.shipment.pk})})


class ShipmentAddContainer(LoginRequiredMixin, SuccessMessageMixin, ModalFormView):
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


class ShipmentAddGroup(LoginRequiredMixin, SuccessMessageMixin, ModalCreateView):
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


class SeatSamples(OwnerRequiredMixin, detail.DetailView):
    template_name = "lims/forms/seat-samples.html"
    model = models.Shipment


class ContainerSpreadsheet(LoginRequiredMixin, detail.DetailView):
    template_name = "lims/forms/container-spreadsheet.html"
    model = models.Container

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if request.user.is_superuser:
            qs = models.Container.objects.all()
        else:
            if not self.request.project:
                qs = models.Container.objects.none()
            else:
                qs = models.Container.objects.filter(project=self.request.project)
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


class SSHKeyCreate(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, ModalCreateView):
    form_class = forms.SSHKeyForm
    model = models.SSHKey
    success_url = '/'
    success_message = "SSH key has been created"

    def test_func(self):
        # Allow access to self or superusers
        target_user = self.get_target_user()
        if not target_user:
            return False
        return self.request.user == target_user or self.request.user.is_superuser

    def get_target_user(self):
        username = self.kwargs.get('username')
        if not username:
            return self.request.user
        return models.User.objects.filter(username=username).first()

    def get_success_url(self):
        if hasattr(self, 'object') and self.object and self.object.user:
            return reverse_lazy('user-detail', kwargs={'username': self.object.user.username})
        return self.success_url

    def get_initial(self):
        initial = super().get_initial()
        target_user = self.get_target_user()
        if not target_user:
            raise http.Http404('User not found')
        initial['user'] = target_user
        return initial


class SSHKeyEdit(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.SSHKeyForm
    model = models.SSHKey
    success_url = '/'
    success_message = "SSH key has been updated"

    def test_func(self):
        obj = self.get_object()
        return self.request.user == obj.user or self.request.user.is_superuser

    def get_success_url(self):
        if hasattr(self, 'object') and self.object and self.object.user:
            return reverse_lazy('user-detail', kwargs={'username': self.object.user.username})
        return self.success_url


class SSHKeyDelete(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, ModalDeleteView):
    model = models.SSHKey
    success_message = "SSH key has been deleted"

    def test_func(self):
        username = self.kwargs.get('username')
        obj = self.get_object()

        if self.request.user.is_superuser:
            return True
        elif obj.user.username == username:
            return True
        return False


class GuideView(detail.DetailView):
    model = models.Guide
    template_name = "lims/modal/guide-youtube.html"

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


class GuideCreate(AdminRequiredMixin, SuccessMessageMixin, ModalCreateView):
    form_class = forms.GuideForm
    model = models.Guide
    success_url = '/'
    success_message = "Guide has been created"


class GuideEdit(AdminRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.GuideForm
    model = models.Guide
    success_url = '/'
    success_message = "Guide has been updated"


class GuideDelete(AdminRequiredMixin, SuccessMessageMixin, ModalDeleteView):
    model = models.Guide
    success_url = '/'
    success_message = "Guide has been deleted"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_action'] = reverse_lazy('guide-delete', kwargs={'pk': self.object.pk})
        return context


def stream_httpx_response(client, response, chunk_size=8192):
    try:
        for chunk in response.iter_bytes(chunk_size=chunk_size):
            yield chunk
    finally:
        response.close()
        client.close()


class ProxyView(View):
    def get(self, request, *args, **kwargs):
        remote_url = settings.DOWNLOAD_PROXY_URL + request.path
        if kwargs.get('section') == 'archive':
            return fetch_archive(request, remote_url)
        client = httpx2.Client()
        req = client.build_request('GET', remote_url, params=request.GET)
        r = client.send(req, stream=True)
        if r.status_code == 200:
            resp = http.StreamingHttpResponse(
                stream_httpx_response(client, r, chunk_size=8192),
                content_type=r.headers.get('Content-Type')
            )
            if 'Content-Disposition' in r.headers:
                resp['Content-Disposition'] = r.headers['Content-Disposition']
            return resp
        try:
            content = r.read()
        finally:
            r.close()
            client.close()
        return http.HttpResponse(content, status=r.status_code, content_type=r.headers.get('Content-Type'))


def fetch_archive(request, url):
    client = httpx2.Client()
    req = client.build_request('GET', url)
    r = client.send(req, stream=True)
    if r.status_code == 200:
        resp = http.StreamingHttpResponse(
            stream_httpx_response(client, r, chunk_size=8192),
            content_type='application/x-gzip'
        )
        resp['Content-Disposition'] = r.headers.get('Content-Disposition', 'attachment; filename=archive.tar.gz')
        return resp
    else:
        r.close()
        client.close()
        return http.HttpResponseNotFound()


class ProjectList(AdminRequiredMixin, ItemListView):
    model = models.Project
    paginate_by = 16
    template_name = "lims/details/user-list.html"
    list_filters = ['created', 'modified', 'kind', 'designation']
    list_columns = ['code', 'title', 'pi', 'kind', 'contact_person', 'contact_phone', 'contact_email']
    list_search = [
        'code', 'title', 'pi__username', 'pi__first_name', 'pi__last_name',
        'contact_person', 'contact_phone', 'contact_email', 'city',
        'region__name', 'region__code', 'country__name', 'country__alpha2', 'country__alpha3',
        'department', 'organisation'
    ]
    link_url = 'project-profile'
    link_kwarg = 'code'
    add_url = 'new-project'
    add_ajax = True
    ordering = ['code']


class UserList(AdminRequiredMixin, ItemListView):
    model = models.User
    paginate_by = 16
    template_name = "lims/list.html"
    list_filters = ['is_active', 'is_superuser']
    list_columns = ['username', 'first_name', 'last_name', 'email', 'is_active', 'is_superuser']
    list_search = ['username', 'first_name', 'last_name', 'email']
    link_url = 'user-detail'
    link_kwarg = 'username'
    page_title = _("Users")
    add_url = 'new-user'
    add_ajax = True
    ordering = ['username']


class AutomounterHistory(AdminRequiredMixin, ListViewMixin, ItemListView):
    model = models.LoadHistory
    template_name = "lims/list.html"
    show_project = False
    list_filters = ['start', 'end']
    list_columns = ['child', 'location', 'start', 'end', ]
    list_search = ['child__name', 'child__project__code', 'location__name', 'parent__container__name']
    page_title = "Load History"

    def get_queryset(self):
        automounter_id = self.kwargs.get('pk')
        automounter = get_object_or_404(models.Automounter, pk=automounter_id)
        self.page_title = f"Load History | {automounter.container.name}"
        return super().get_queryset().filter(parent_id=automounter_id).order_by('-start')


class ContainerHistory(UserPassesTestMixin, ListViewMixin, ItemListView):
    model = models.LoadHistory
    template_name = "lims/list.html"
    show_project = False
    list_filters = ['start', 'end']
    list_columns = ['parent', 'location', 'start', 'end', ]
    list_search = ['parent__name', 'child__name', 'child__project__code', 'location__name', 'parent__container__name']
    page_title = "Load History"

    def test_func(self) -> bool | None:
        container_id = self.kwargs.get('pk')
        obj = get_object_or_404(models.Container, pk=container_id)

        if obj:
            self.page_title = f"Load History | {obj.name}"
            return self.request.user.can_access_project(obj.project)

        return False

    def get_queryset(self):
        container_id = self.kwargs.get('pk')
        return super().get_queryset().filter(child_id=container_id).order_by('-start')


class ProjectInfo(LoginRequiredMixin, UserPassesTestMixin, detail.DetailView):
    model = models.Project
    template_name = "lims/modal/project-info.html"

    def test_func(self) -> bool | None:
        try:
            return self.request.user.can_access_project(self.get_object())
        except models.Project.DoesNotExist:
            return False

    def get_object(self, **kwargs):
        code = self.kwargs.get('code') or self.kwargs.get('name') or self.kwargs.get('username')
        obj = models.Project.objects.filter(
            models.Q(code=code)
        ).first()
        if not obj:
            raise models.Project.DoesNotExist(f"Project matching {code} does not exist.")
        return obj


class ProjectProfile(ProjectInfo):
    template_name = "lims/details/project.html"
    page_title = "Project Profile"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = stats.project_stats(self.object)
        return context


class ProjectCreate(AdminRequiredMixin, SuccessMessageMixin, ModalCreateView):
    form_class = forms.NewProjectForm
    model = models.Project
    success_url = reverse_lazy('user-list')
    success_message = "New Project '%(code)s' has been created."

    def form_valid(self, form):
        response = super().form_valid(form)
        models.ActivityLog.objects.log_activity(
            self.request, self.object, models.ActivityLog.TYPE.CREATE,
            f'New Project {self.object} added'
        )
        return response


class ProjectDelete(AdminRequiredMixin, SuccessMessageMixin, ModalDeleteView):
    model = models.Project
    success_url = reverse_lazy('user-list')
    success_message = "Project has been deleted"

    def test_func(self):
        if not super().test_func():
            return False
        try:
            obj = self.get_object()
        except models.Project.DoesNotExist:
            return True
        return not bool(obj.source_id)

    def get_object(self, *kwargs):
        code = self.kwargs.get('code') or self.kwargs.get('name') or self.kwargs.get('username')
        obj = self.model.objects.get(code=code)
        return obj

    def get_context_data(self, **kwargs):
        context = super(ProjectDelete, self).get_context_data(**kwargs)
        context['form_action'] = reverse_lazy('project-delete', kwargs={'code': self.object.code})
        return context

    def confirmed(self, *args, **kwargs):
        code = self.kwargs.get('code') or self.kwargs.get('name') or self.kwargs.get('username')
        self.success_message = f"{code} project has been deleted"
        return super().confirmed(*args, **kwargs)


class UserDetailView(LoginRequiredMixin, UserPassesTestMixin, detail.DetailView):
    model = models.User
    slug_field = 'username'
    slug_url_kwarg = 'username'
    template_name = "lims/details/user.html"

    def test_func(self):
        target = self.get_object()
        return self.request.user == target or self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['projects'] = self.object.get_projects()
        context['sshkeys'] = self.object.sshkeys.all()
        context['activities'] = self.object.activities.all().order_by('-created')[:12]
        return context


class UserEditView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, ModalUpdateView):
    model = models.User
    slug_field = 'username'
    slug_url_kwarg = 'username'
    form_class = forms.UserEditForm
    success_message = _("Profile has been updated.")

    def test_func(self):
        target = self.get_object()
        return self.request.user == target or self.request.user.is_superuser

    def get_success_url(self):
        return reverse_lazy('user-detail', kwargs={'username': self.object.username})


class SwitchProjectView(LoginRequiredMixin, View):
    """
    Dedicated view to switch the user's active project context in session and database.
    """
    def _switch(self, request, project_id, next_url=None):
        if not project_id:
            raise Http404(_("No project specified."))

        project = get_object_or_404(models.Project, pk=project_id)

        # Access check: superuser or project member or PI
        is_authorized = (
            request.user.is_superuser
            or project.members.filter(pk=request.user.pk).exists()
            or project.pi_id == request.user.pk
        )
        if not is_authorized:
            raise PermissionDenied(_("You do not have access to this project."))

        if hasattr(request, 'session'):
            request.session['active_project_id'] = project.pk

        if request.user.is_authenticated:
            request.user.default_project = project
            request.user.save(update_fields=['default_project'])

        # Safe redirection
        redirect_to = '/'
        return HttpResponseRedirect(redirect_to)

    def get(self, request, pk=None):
        project_id = pk or request.GET.get('project_id')
        return self._switch(request, project_id, next_url=request.GET.get('next'))

    def post(self, request, pk=None):
        project_id = pk or request.POST.get('project_id')
        return self._switch(request, project_id, next_url=request.POST.get('next'))


class EditSettings(AdminRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    model = models.SystemSettings
    form_class = forms.SystemSettingsForm
    success_message = _("System Settings updated.")

    def get_object(self, queryset=None):
        self.kwargs['pk'] = 1
        return super().get_object(queryset=queryset)


def record_logout(sender, user, request, **kwargs):
    """ user logged outof the system """
    models.ActivityLog.objects.log_activity(
        request, user, models.ActivityLog.TYPE.LOGOUT, f'{user.name} logged-out'
    )


def record_login(sender, user, request, **kwargs):
    """ Login a user into the system """
    if user.is_authenticated:
        models.ActivityLog.objects.log_activity(
            request, user, models.ActivityLog.TYPE.LOGIN, f'{user.name} logged-in'
        )
        last_login = models.ActivityLog.objects.last_login(request, user=user)
        try:
            if last_login is not None:
                last_host = last_login.ip_number
                login_time = timezone.localtime(last_login.created)
                message = f'Your previous login was on {dateformat.format(login_time, "M jS @ P")} from {last_host}.'
                messages.info(request, message)
            elif not user.is_staff:
                message = 'You are logging in for the first time. Please make sure your profile is updated.'
                messages.info(request, message)
        except Exception:
            pass


user_logged_in.connect(record_login)
user_logged_out.connect(record_logout)


@method_decorator(never_cache, name='dispatch')
class PuckLoader(AdminRequiredMixin, detail.DetailView):
    model = models.Beamline
    template_name = "lims/loader.html"

    def get_object(self, queryset=None):
        acronym = self.kwargs.get('beamline')
        return models.Beamline.objects.get(acronym__iexact=acronym)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        automounter = self.object.active_automounter()
        config, created = models.LoaderConfig.objects.get_or_create(
            beamline=self.object, automounter=automounter
        )
        context['config'] = config
        context['projects'] = models.Project.objects.filter(
            shipments__status=models.Shipment.STATES.ON_SITE,
        )
        models.LoaderConfig.objects.filter(pk=config.pk).update(pending=False)
        if self.kwargs.get('project'):
            proj_ident = self.kwargs['project']
            project = models.Project.objects.filter(models.Q(code=proj_ident) | models.Q(id=int(proj_ident) if str(proj_ident).isdigit() else -1)).first()
            if project:
                context['active_project'] = project
                context['containers'] = project.containers.on_site().order_by('name')
        return context


@method_decorator(csrf_exempt, name='dispatch')
class SelectPuck(AuthenticationRequiredMixin, View):

    def post(self, request, *args, **kwargs):
        beamline = kwargs.get('beamline')
        project = kwargs.get('project')
        puck = kwargs.get('puck')

        beamline = models.Beamline.objects.get(acronym__iexact=beamline)
        project = models.Project.objects.filter(models.Q(code__iexact=project) | models.Q(id=int(project) if str(project).isdigit() else -1)).first() or models.Project.objects.get(code__iexact=project)
        puck = project.containers.on_site().filter(pk=puck).first()
        if not puck:
            messages.error(request, 'Puck not found')
            return JsonResponse({"url": "", "error": "Puck not found"})

        config, created = models.LoaderConfig.objects.get_or_create(
            beamline=beamline, automounter=beamline.active_automounter()
        )
        elapsed = timezone.now() - config.modified
        if config.selected and elapsed.total_seconds() > settings.LOADER_SELECT_DURATION:
            config.selected = None
            config.save()

        if not config.automounter.container.accepts(puck):
            messages.error(request, 'Puck not accepted by automounter')
            return JsonResponse({"url": "", 'error': "Puck not accepted by automounter"})

        if config.selected != puck:
            config.selected = puck
            config.save()
        elif config.selected == puck:
            config.selected = None
            config.save()
        return JsonResponse({
            'url': reverse('project-puck-loader', kwargs={'beamline': beamline.acronym, 'project': project.name})
        })


class LoadPuck(AuthenticationRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        acronym = kwargs.get('beamline')
        position = kwargs.get('position')

        config = models.LoaderConfig.objects.filter(beamline__acronym=acronym).first()
        if not config:
            return http.HttpResponseBadRequest("Automounter not found")

        if not config.selected:
            return http.HttpResponseBadRequest("No puck selected")

        elapsed = timezone.now() - config.modified
        if elapsed.total_seconds() > settings.LOADER_SELECT_DURATION:
            return http.HttpResponseBadRequest("Puck selection expired")

        location = config.automounter.kind.locations.filter(name=position).first()
        if not location:
            return http.HttpResponseBadRequest("Invalid Position")

        puck = config.selected
        config.selected = None
        config.pending = True
        config.save()

        # remove an existing puck from position
        existing_puck = config.automounter.children.filter(location=location).first()
        if existing_puck:
            models.LoadHistory.objects.filter(child=existing_puck).active().update(end=timezone.now())
            models.Container.objects.filter(pk=existing_puck.pk).update(parent=None, location=None)

        models.LoadHistory.objects.create(child=puck, parent=config.automounter, location=location)
        models.Container.objects.filter(pk=puck.pk).update(parent=config.automounter, location=location)

        return JsonResponse({'loaded': puck.name, 'location': location.name})


class UnloadPuck(AuthenticationRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        acronym = kwargs.get('beamline')
        position = kwargs.get('position')

        config = models.LoaderConfig.objects.filter(beamline__acronym=acronym).first()
        if not config:
            return http.HttpResponseBadRequest("Automounter not found")

        location = config.automounter.kind.locations.filter(name=position).first()
        if not location:
            return http.HttpResponseBadRequest("Invalid location")

        puck = config.automounter.children.filter(location=location).first()
        if not puck:
            return http.HttpResponseBadRequest("No puck found at this location")

        config.selected = puck  # Set the selected puck to the one being unloaded in case we need to reload it
        config.save()

        models.LoadHistory.objects.filter(child=puck).active().update(end=timezone.now())
        models.Container.objects.filter(pk=puck.pk).update(parent=None, location=None)

        return JsonResponse({'unloaded': puck.name, 'location': location.name})


class CheckPending(AuthenticationRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        acronym = kwargs.get('beamline')
        config = models.LoaderConfig.objects.filter(beamline__acronym=acronym).first()
        if not config:
            return JsonResponse({'pending': False})

        return JsonResponse({'pending': config.pending})


def custom_403_view(request, exception=None):
    return render(request, "lims/warning.html", {
       "status_code": 403,
       "error_title": "Access Denied",
       "error_message": (
           "You lack the required authorization to view this resource."
       ),
       "request_id": f"REQ-{uuid.uuid4().hex[:8].upper()}",
       "exception": str(exception),
    }, status=403)


def custom_404_view(request, exception=None):
    return render(request, "lims/warning.html", {
       "status_code": 404,
       "error_title": "Lost in Cyberspace",
       "error_message": (
           "The resource you requested may have moved, been deleted, or "
           "does not exist at this address. Check the URL for errors."
       ),
       "request_id": f"REQ-{uuid.uuid4().hex[:8].upper()}",
       "exception": str(exception),
    }, status=404)


def custom_500_view(request):
    return render(request, "lims/warning.html", {
       "status_code": 500,
       "error_title": "Server Encountered an Error",
       "error_message": (
           "A critical unexpected server failure was encountered. "
           "Our automated monitoring infrastructure has logged this event."
       ),
       "request_id": f"REQ-{uuid.uuid4().hex[:8].upper()}",
    }, status=500)
