import re
import json

from operator import itemgetter
from collections import defaultdict

from django import http
from django.db import transaction
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.views.generic import View

from basiclive.utils.mixins import LoginRequiredMixin, AdminRequiredMixin
from . import models

@method_decorator(csrf_exempt, name='dispatch')
class FetchReport(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        try:
            report = models.AnalysisReport.objects.get(pk=kwargs.get('pk'))
        except models.AnalysisReport.DoesNotExist:
            raise http.Http404("Report does not exist.")

        if report.project != request.user and not request.user.is_superuser:
            raise http.Http404()

        return JsonResponse({'details': report.details}, safe=False)


@method_decorator(csrf_exempt, name='dispatch')
class FetchRequest(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        try:
            experiment_request = models.Request.objects.get(pk=request.GET.get('pk'))
        except models.Request.DoesNotExist:
            raise http.Http404("Request does not exist.")

        if experiment_request.project != request.user and not request.user.is_superuser:
            raise http.Http404()

        return JsonResponse(experiment_request.json_dict(), safe=False)


@method_decorator(csrf_exempt, name='dispatch')
class UpdatePriority(LoginRequiredMixin, View):

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        try:
            group = models.Group.objects.get(pk=request.POST.get('group'))
        except models.Group.DoesNotExist:
            raise http.Http404("Group does not exist.")

        if group.project != request.user:
            raise http.Http404()

        pks = [int(u) for u in request.POST.getlist('samples[]') if u]
        priorities = {
            pk: i + 1
            for i, pk in enumerate(pks)
        }

        to_update = []
        for sample in group.samples.all():
            new_priority = priorities.get(sample.pk, sample.priority)
            if sample.priority != new_priority:
                sample.priority = new_priority
                to_update.append(sample)

        group.samples.bulk_update(to_update, fields=["priority"])

        return JsonResponse([], safe=False)


@method_decorator(csrf_exempt, name='dispatch')
class UpdateRequestPriority(LoginRequiredMixin, View):

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        try:
            shipment = models.Shipment.objects.get(pk=request.POST.get('shipment'))
        except models.Shipment.DoesNotExist:
            raise http.Http404("Shipment does not exist.")

        if shipment.project != request.user:
            raise http.Http404()

        pks = [int(u) for u in request.POST.getlist('priorities[]') if u]
        priorities = {
            pk: i + 1
            for i, pk in enumerate(pks)
        }

        to_update = []
        for request in shipment.requests():
            new_priority = priorities.get(request.pk, request.priority)
            if request.priority != new_priority:
                request.priority = new_priority
                to_update.append(request)

        shipment.requests().bulk_update(to_update, fields=["priority"])

        return JsonResponse([], safe=False)


@method_decorator(csrf_exempt, name='dispatch')
class UpdateGroupPriority(LoginRequiredMixin, View):

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        try:
            shipment = models.Shipment.objects.get(pk=request.POST.get('shipment'))
        except models.Shipment.DoesNotExist:
            raise http.Http404("Shipment does not exist.")

        if shipment.project != request.user:
            raise http.Http404()

        pks = [int(u) for u in request.POST.getlist('priorities[]') if u]
        priorities = {
            pk: i + 1
            for i, pk in enumerate(pks)
        }

        to_update = []
        for group in shipment.groups.all():
            new_priority = priorities.get(group.pk, group.priority)
            if group.priority != new_priority:
                group.priority = new_priority
                to_update.append(group)

        shipment.groups.all().bulk_update(to_update, fields=["priority"])

        return JsonResponse([], safe=False)


@method_decorator(csrf_exempt, name='dispatch')
class BulkSampleEdit(LoginRequiredMixin, View):

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        errors = []

        group = request.POST.get('group')
        if models.Group.objects.get(pk=group).project.username != self.request.user.username:
            errors.append('You do not have permission to modify these samples.')
            return JsonResponse(errors, safe=False)

        data = {}
        i = 0
        while request.POST.getlist('samples[{}][]'.format(i)):
            info = request.POST.getlist('samples[{}][]'.format(i))
            data[info[0]] = {'name': info[1], 'barcode': info[2], 'comments': info[3]}
            i += 1

        for name in set([v['name'] for v in data.values()]):
            if not re.compile('^[a-zA-Z0-9-_]+$').match(name):
                errors.append('{}: Names cannot contain any spaces or special characters'.format(name.encode('utf-8')))

        names = list(
            models.Sample.objects.filter(group__pk=group).exclude(pk__in=data.keys()).values_list('name', flat=True))
        names.extend([v['name'] for v in data.values()])

        duplicates = set([name for name in names if names.count(name) > 1])
        for name in duplicates:
            errors.append('{}: Each sample in the group must have a unique name'.format(name))

        if not errors:
            for pk, info in data.items():
                models.Sample.objects.filter(pk=pk).update(**info)

        return JsonResponse(errors, safe=False)


class UpdateLocations(AdminRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        container = models.Container.objects.get(pk=self.kwargs['pk'])
        locations = list(container.kind.locations.values_list('pk', 'name'))
        return JsonResponse(locations, safe=False)


class FetchContainerLayout(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        if request.user.is_superuser:
            qs = models.Container.objects.filter()
        else:
            qs = models.Container.objects.filter(project=self.request.user)

        try:
            container = qs.get(pk=self.kwargs['pk'])
            return JsonResponse(container.get_layout(), safe=False)
        except models.Container.DoesNotExist:
            raise http.Http404('Container Not Found!')


class UnloadContainer(AdminRequiredMixin, View):

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        try:
            container = models.Container.objects.get(pk=self.kwargs['pk'])
            root = models.Container.objects.get(pk=self.kwargs['root'])
        except models.Group.DoesNotExist:
            raise http.Http404("Can't unload Container.")

        models.LoadHistory.objects.filter(child=self.kwargs['pk']).active().update(end=timezone.now())
        models.Container.objects.filter(pk=container.pk).update(parent=None, location=None)

        return JsonResponse(root.get_layout(), safe=False)


class CreateShipmentSamples(LoginRequiredMixin, View):

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if request.user.is_superuser:
            qs = models.Shipment.objects.filter()
        else:
            qs = models.Shipment.objects.filter(project=self.request.user)
        try:
            shipment = qs.get(pk=self.kwargs['pk'])
            samples = json.loads(request.POST.get('samples', '[]'))
            grouped_samples = defaultdict(list)
            loc_info = {
                container.pk: dict(container.kind.locations.values_list('name', 'pk'))
                for container in shipment.containers.all()
            }
            for sample in sorted(samples, key=itemgetter('container', 'location')):
                grouped_samples[sample['group']].append(
                    {
                        'project': shipment.project,
                        'container_id': sample['container'],
                        'location_id': sample.get('location') and loc_info[sample['container']][str(sample['location'])] or None
                    }
                )

            to_create = []
            models.Sample.objects.filter(container__shipment=shipment).delete()
            for group in shipment.groups.all():
                # remove existing samples
                for i, details in enumerate(grouped_samples.get(group.pk, [])):
                    to_create.append(models.Sample(name='{}_{}'.format(group.name, i + 1), group=group, **details))
            shipment.project.samples.bulk_create(to_create)
            return JsonResponse({'url': shipment.get_absolute_url()}, safe=False)
        except models.Shipment.DoesNotExist:
            raise http.Http404('Shipment Not Found!')


class SaveContainerSamples(LoginRequiredMixin, View):

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
                    'group': group_map[group_name],
                    'location_id': sample['location'],
                    'container': container,
                    'barcode': sample['barcode'],
                    'comments': sample['comments'],
                }
                if sample.get('name') and sample.get('sample'):  # update entries
                    models.Sample.objects.filter(project=container.project, pk=sample.get('sample')).update(**info)
                elif sample.get('name'):  # create new entry
                    models.Sample.objects.create(project=container.project, **info)
                else:   # delete existing entry
                    models.Sample.objects.filter(
                        project=container.project, location_id=sample['location'], container=container
                    ).delete()

            return JsonResponse({'url': container.get_absolute_url()}, safe=False)
        except models.Container.DoesNotExist:
            raise http.Http404('Container Not Found!')