from django.views.generic import TemplateView
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import edit, detail
from django.contrib.auth.mixins import UserPassesTestMixin
from django.utils import timezone
from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.clickjacking import xframe_options_exempt, xframe_options_sameorigin

from ...utils import filters
from basiclive.utils.mixins import AsyncFormMixin, AdminRequiredMixin, LoginRequiredMixin, PlotViewMixin

from . import models, forms, stats
from itemlist.views import ItemListView
from basiclive.core.lims.models import Beamline
from basiclive.core.lims.views import ListViewMixin

from datetime import datetime, timedelta

MIN_SUPPORT_HOUR = getattr(settings, 'MIN_SUPPORT_HOUR', 0)
MAX_SUPPORT_HOUR = getattr(settings, 'MAX_SUPPORT_HOUR', 24)


class CalendarView(TemplateView):
    template_name = 'schedule/public-schedule.html'

    @xframe_options_exempt
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        detailed = self.request.GET.get('detailed', False)
        now = self.request.GET.get('start') and datetime.strptime(self.request.GET['start'], '%Y-%m-%dT%H') or timezone.localtime()
        try:
            d = '{}-W{}-1'.format(kwargs.get('year', ''), kwargs.get('week', ''))
            now = datetime.strptime(d, '%G-W%V-%w')
        except:
            pass

        (year, week, _) = now.isocalendar()
        context['today'] = datetime.strftime(timezone.localtime(), '%Y-%m-%d')
        context['year'] = year
        context['week'] = week
        context['support'] = "{:02d}:00 - {:02d}:00".format(MIN_SUPPORT_HOUR, MAX_SUPPORT_HOUR)
        context['beamlines'] = Beamline.objects.filter(active=True)
        context['access_types'] = models.AccessType.objects.all()
        context['facility_modes'] = models.FacilityMode.objects.all()
        context['scope_types'] = [(s[1].replace(' ', ''), s[1]) for s in models.Downtime.SCOPE_CHOICES]
        context['next_week'] = (now + timedelta(days=7)).isocalendar()[:2]
        context['last_week'] = (now - timedelta(days=7)).isocalendar()[:2]
        context['editable'] = detailed

        return context


class ScheduleView(LoginRequiredMixin, CalendarView):
    template_name = 'schedule/schedule.html'

    @xframe_options_sameorigin
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['editable'] = self.request.user.is_superuser
        return context


class BeamtimeInfo(LoginRequiredMixin, UserPassesTestMixin, detail.DetailView):
    model = models.Beamtime
    template_name = "schedule/beamtime-info.html"

    def test_func(self):
        # Allow access to admin or owner
        return self.request.user.is_superuser or self.get_object().project == self.request.user


class BeamtimeStats(PlotViewMixin, ListViewMixin, ItemListView):
    model = models.Beamtime
    list_filters = ['beamline', filters.YearFilterFactory('start'), filters.MonthFilterFactory('start'),
                    filters.QuarterFilterFactory('start'), 'access', 'project__kind', filters.TimeScaleFilterFactory()]
    list_search = ['id', 'project__username', 'project__first_name', 'project__last_name']
    date_field = 'start'

    def get_metrics(self):
        return stats.beamtime_stats(self.get_queryset(), self.get_active_filters())


class BeamtimeCreate(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.CreateView):
    form_class = forms.BeamtimeForm
    template_name = "modal/form.html"
    model = models.Beamtime
    success_url = reverse_lazy('schedule')
    success_message = "Beamtime has been created"

    def get_initial(self):
        initial = super().get_initial()
        try:
            start = timezone.make_aware(datetime.strptime(self.request.GET.get('start'), "%Y-%m-%dT%H"))
            end = timezone.make_aware(datetime.strptime(self.request.GET.get('end'), "%Y-%m-%dT%H") + timedelta(hours=settings.HOURS_PER_SHIFT))
            beamline = Beamline.objects.filter(acronym=self.request.GET.get('beamline')).first()
            info = {'start': start, 'end': end, 'beamline': beamline}
            if models.Beamtime.objects.filter(beamline=beamline).filter((
                Q(start__gte=start) & Q(start__lt=end)) | (
                Q(end__lte=end) & Q(end__gt=start)) | (
                Q(start__gte=start) & Q(end__lte=end))).exists():
                    info['warning'] = """Another project is scheduled in this time. Proceeding to schedule this beamtime 
                                         will remove the existing beamtime."""

            initial.update(**info)
        except:
            pass

        return initial

    def form_valid(self, form):
        super().form_valid(form)
        obj = self.object

        models.Beamtime.objects.filter(beamline=obj.beamline).filter(
            Q(start__lt=obj.start) & Q(end__gt=obj.start)).update(**{'end': obj.start})
        models.Beamtime.objects.filter(beamline=obj.beamline).filter(
            Q(start__lt=obj.end) & Q(end__gt=obj.end)).update(**{'start': obj.end})
        models.Beamtime.objects.filter(beamline=obj.beamline).filter((
            Q(start__gte=obj.start) & Q(start__lt=obj.end)) | (
            Q(end__lte=obj.end) & Q(end__gt=obj.start)) | (
            Q(start__gte=obj.start) & Q(end__lte=obj.end))).exclude(pk=obj.pk).delete()

        if form.cleaned_data['notify']:
            models.EmailNotification.objects.create(beamtime=self.object)

        success_url = self.get_success_url()
        return JsonResponse({'url': success_url})


class BeamtimeEdit(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.BeamtimeForm
    template_name = "modal/form.html"
    model = models.Beamtime
    success_url = reverse_lazy('schedule')
    success_message = "Beamtime has been updated"

    def get_initial(self):
        initial = super().get_initial()
        initial['notify'] = self.object.notifications.exists()
        return initial

    def get_success_url(self):
        success_url = super().get_success_url()
        return '{}?start={}'.format(success_url, datetime.strftime(self.object.start, '%Y-%m-%dT%H'))

    def form_valid(self, form):
        super().form_valid(form)
        obj = self.object

        obj.notifications.filter(sent=False).delete()
        if form.cleaned_data['notify']:
            models.EmailNotification.objects.create(beamtime=obj)

        models.Beamtime.objects.filter(beamline=obj.beamline).filter(
            Q(start__lt=obj.start) & Q(end__gt=obj.start)).update(**{'end': obj.start})
        models.Beamtime.objects.filter(beamline=obj.beamline).filter(
            Q(start__lt=obj.end) & Q(end__gt=obj.end)).update(**{'start': obj.end})
        models.Beamtime.objects.filter(beamline=obj.beamline).filter((
            Q(start__gte=obj.start) & Q(start__lt=obj.end)) | (
            Q(end__lte=obj.end) & Q(end__gt=obj.start)) | (
            Q(start__gte=obj.start) & Q(end__lte=obj.end))).exclude(pk=obj.pk).delete()

        success_url = self.get_success_url()
        return JsonResponse({'url': success_url})


class BeamtimeDelete(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.DeleteView):
    template_name = "modal/delete.html"
    model = models.Beamtime
    success_url = reverse_lazy('schedule')
    success_message = "Beamtime has been deleted"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_action'] = reverse_lazy('beamtime-delete', kwargs={'pk': self.object.pk})
        return context

    def get_success_url(self):
        success_url = super().get_success_url()
        return '{}?start={}'.format(success_url, datetime.strftime(self.object.start, '%Y-%m-%dT%H'))

    def delete(self, request, *args, **kwargs):
        super().delete(request, *args, **kwargs)
        success_url = self.get_success_url()
        return JsonResponse({'url': success_url})


class SupportDetail(LoginRequiredMixin, detail.DetailView):
    model = models.BeamlineSupport
    template_name = "schedule/templates/schedule/support-info.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['current'] = self.request.GET.get('current') == 'True'
        return ctx


class SupportCreate(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.CreateView):
    form_class = forms.BeamlineSupportForm
    template_name = "modal/form.html"
    model = models.BeamlineSupport
    success_url = reverse_lazy('schedule')
    success_message = "Beamline Support has been created"

    def get_initial(self):
        initial = super().get_initial()
        dt = self.request.GET.get('date')
        if dt:
            initial['date'] = datetime.strptime(dt, "%Y-%m-%d")

        return initial


class SupportEdit(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.BeamlineSupportForm
    template_name = "modal/form.html"
    model = models.BeamlineSupport
    success_url = reverse_lazy('schedule')
    success_message = "Beamline Support has been updated"


class SupportDelete(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.DeleteView):
    template_name = "modal/delete.html"
    model = models.BeamlineSupport
    success_url = reverse_lazy('schedule')
    success_message = "Beamline Support has been deleted"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_action'] = reverse_lazy('support-delete', kwargs={'pk': self.object.pk})
        return context

    def delete(self, request, *args, **kwargs):
        super().delete(request, *args, **kwargs)
        success_url = self.get_success_url()
        return JsonResponse({'url': success_url})


def split_visits(obj, start, end):

    originals = models.Beamtime.objects.filter(beamline=obj.beamline).filter((Q(end__lte=end) & Q(end__gt=start))).filter(start__lt=start)
    for bt in originals:
        clone_info = {f.name: getattr(bt, f.name) for f in bt._meta.fields}
        clone_info.update({'id': None, 'start': start})
        clone = models.Beamtime(**clone_info)
        clone.save()
        bt.end = start
        bt.save()

    originals = models.Beamtime.objects.filter(beamline=obj.beamline).filter((Q(start__lt=end) & Q(start__gte=start))).filter(end__gt=end)
    for bt in originals:
        clone_info = {f.name: getattr(bt, f.name) for f in bt._meta.fields}
        clone_info.update({'id': None, 'end': end})
        clone = models.Beamtime(**clone_info)
        clone.save()
        bt.start = end
        bt.save()

    originals = models.Beamtime.objects.filter(beamline=obj.beamline).filter(start__lt=start).filter(end__gt=end)
    for bt in originals:
        clone1_info = {f.name: getattr(bt, f.name) for f in bt._meta.fields}
        clone1_info.update({'id': None, 'end': end})
        clone1 = models.Beamtime(**clone1_info)
        clone1.save()

        clone2_info = {f.name: getattr(bt, f.name) for f in bt._meta.fields}
        clone2_info.update({'id': None, 'start': end})
        clone2 = models.Beamtime(**clone2_info)
        clone2.save()

        bt.start = start
        bt.end = end
        bt.save()


class DowntimeCreate(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.CreateView):
    form_class = forms.DowntimeForm
    template_name = "modal/form.html"
    model = models.Downtime
    success_url = reverse_lazy('schedule')
    success_message = "Downtime has been created"

    def get_initial(self):
        initial = super().get_initial()
        try:
            start = datetime.strptime(self.request.GET.get('start'), "%Y-%m-%dT%H")
            end = datetime.strptime(self.request.GET.get('end'), "%Y-%m-%dT%H") + timedelta(hours=settings.HOURS_PER_SHIFT)
            beamline = Beamline.objects.filter(acronym=self.request.GET.get('beamline')).first()
            info = {'start': start, 'end': end, 'beamline': beamline}

            initial.update(**info)
        except:
            pass

        return initial

    def form_valid(self, form):
        super().form_valid(form)
        obj = self.object

        split_visits(obj, obj.start, obj.end)
        models.Beamtime.objects.filter(beamline=obj.beamline).filter(
            (Q(start__gte=obj.start) & Q(end__lte=obj.end))).update(cancelled=True)

        success_url = self.get_success_url()
        return JsonResponse({'url': success_url})


class DowntimeEdit(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.DowntimeForm
    template_name = "modal/form.html"
    model = models.Downtime
    success_url = reverse_lazy('schedule')
    success_message = "Downtime has been updated"

    def form_valid(self, form):
        fv = super().form_valid(form)
        obj = form.instance

        if form.data.get('submit') == 'Delete':
            models.Beamtime.objects.filter(beamline=obj.beamline, start__gte=obj.start, end__lte=obj.end).update(cancelled=False)
            obj.delete()
            self.success_message = "Downtime has been deleted"
        else:
            if obj.start < form.initial['start']:
                start = obj.start
                end = form.initial['start']

                split_visits(obj, start, end)
                models.Beamtime.objects.filter(beamline=obj.beamline).filter(
                    (Q(start__gte=start) & Q(end__lte=end))).update(cancelled=True)
            if obj.end > form.initial['end']:
                start = form.initial['end']
                end = obj.end

                split_visits(obj, start, end)
                models.Beamtime.objects.filter(beamline=obj.beamline).filter(
                    (Q(start__gte=start) & Q(end__lte=end))).update(cancelled=True)

        return fv


class EmailNotificationList(AdminRequiredMixin, ListViewMixin, ItemListView):
    model = models.EmailNotification
    list_filters = ['send_time', 'sent']
    list_columns = ['id', 'sent', 'unsendable', 'send_time', 'beamtime__start', 'beamtime__project__username', 'email_subject']
    list_search = ['email_subject', 'email_body']
    link_url = 'email-edit'
    ordering = ['-send_time']
    ordering_proxies = {}
    list_transforms = {}
    show_project = False
    link_attr = 'data-link'

    def get_queryset(self):
        return super().get_queryset()


class EmailNotificationEdit(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.EmailNotificationForm
    template_name = "modal/form.html"
    model = models.EmailNotification
    success_url = reverse_lazy('schedule')
    success_message = "Email Notification has been updated"

    def get_initial(self):
        initial = super().get_initial()
        initial['recipients'] = '; '.join(self.object.recipient_list())
        if self.object.unsendable():
            initial['warning'] = "This email cannot be sent. Either the send time has already passed, the beamtime has been cancelled, or there are no recipients."

        return initial