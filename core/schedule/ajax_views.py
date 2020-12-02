from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View
from django.http import JsonResponse
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from datetime import datetime

from .models import Beamtime, Downtime


@method_decorator(csrf_exempt, name='dispatch')
class FetchBeamtime(View):

    def get(self, request, *args, **kwargs):
        start = request.GET.get('start', False)
        end = request.GET.get('end', False)
        detailed = request.GET.get('detailed', False)

        start = start and timezone.make_aware(datetime.strptime(start, '%Y-%m-%d')) or False
        end = end and timezone.make_aware(datetime.strptime(end, '%Y-%m-%d')) or False

        queryset = Beamtime.objects.filter()
        if start and end:
            queryset = queryset.filter((
                Q(start__lte=start) & Q(end__gte=end)) | (
                Q(start__gte=start) & Q(start__lt=end)) | (
                Q(end__lte=end) & Q(end__gt=start)) | (
                Q(start__gte=start) & Q(end__lte=end)))
        elif start:
            queryset = queryset.filter(start__gte=start)
        elif end:
            queryset = queryset.filter(end__lte=end)

        resp = []
        for bt in queryset:
            field = {
                "id": bt.pk,
                "title": bt.display(detailed),
                "comments": bt.comments,
                "beamline": bt.beamline.acronym,
                "url": '',
                "css_class": "{} {}".format(bt.access and bt.access.name or "", bt.cancelled and 'cancelled' or ''),
                "starts": bt.start_times,
                "end": bt.end_time
            }
            resp.append(field)
        return JsonResponse(resp, safe=False)


@method_decorator(csrf_exempt, name='dispatch')
class FetchDowntime(View):

    def get(self, request, *args, **kwargs):
        start = request.GET.get('start', False)
        end = request.GET.get('end', False)

        start = start and timezone.make_aware(datetime.strptime(start, '%Y-%m-%d')) or False
        end = end and timezone.make_aware(datetime.strptime(end, '%Y-%m-%d')) or False

        queryset = Downtime.objects.filter()
        if start and end:
            queryset = queryset.filter((
                Q(start__gte=start) & Q(start__lt=end)) | (
                Q(end__lte=end) & Q(end__gt=start)) | (
                Q(start__gte=start) & Q(end__lte=end)) | (
                Q(start__lte=start) & Q(end__gte=end)
            ))
        elif start:
            queryset = queryset.filter(start__gte=start)
        elif end:
            queryset = queryset.filter(end__lte=end)

        resp = []
        for bt in queryset:
            field = {
                "id": bt.pk,
                "beamline": bt.beamline.acronym,
                "style": bt.get_scope_display().replace(' ', ''),
                "comments": bt.comments,
                "url": reverse('downtime-edit', kwargs={'pk': bt.pk}),
                "starts": bt.start_times,
                "end": bt.end_time
            }
            resp.append(field)
        return JsonResponse(resp, safe=False)