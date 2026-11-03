import logging
from datetime import datetime, timedelta

from crisp_modals.views import ModalCreateView, ModalUpdateView, ModalDeleteView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt, xframe_options_sameorigin
from django.views.generic import TemplateView
from django.views.generic import detail
from itemlist.views import ItemListView

from basiclive.core.lims.models import Beamline
from basiclive.core.lims.views import ListViewMixin
from basiclive.core.schedule.conf import settings
from basiclive.utils.mixins import AdminRequiredMixin, LoginRequiredMixin
from . import models, forms

MIN_SUPPORT_HOUR = settings.MIN_SUPPORT_HOUR
MAX_SUPPORT_HOUR = settings.MAX_SUPPORT_HOUR


logger = logging.getLogger(__name__)


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
        context['support'] = f"{MIN_SUPPORT_HOUR:02d}:00 - {MAX_SUPPORT_HOUR:02d}:00"
        context['beamlines'] = Beamline.objects.filter(active=True, simulated=False)
        context['access_types'] = models.AccessType.objects.all()
        context['facility_modes'] = models.FacilityModeType.objects.all()
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


class BeamtimeCreate(AdminRequiredMixin, SuccessMessageMixin, ModalCreateView):
    form_class = forms.BeamtimeForm
    model = models.Beamtime
    success_url = reverse_lazy('schedule')
    success_message = "Beamtime has been created"

    def get_initial(self):
        initial = super().get_initial()
        try:
            start = timezone.make_aware(datetime.strptime(self.request.GET.get('start'), "%Y-%m-%dT%H"))
            end = timezone.make_aware(
                datetime.strptime(self.request.GET.get('end'), "%Y-%m-%dT%H")
                + timedelta(hours=settings.HOURS_PER_SHIFT)
            )
            beamline = Beamline.objects.filter(acronym=self.request.GET.get('beamline')).first()
            info = {'start': start, 'end': end, 'beamline': beamline}
            scheduled_filter = (
                (Q(start__gte=start) & Q(start__lt=end)) |
                (Q(end__lte=end) & Q(end__gt=start)) |
                (Q(start__gte=start) & Q(end__lte=end))
            )
            if models.Beamtime.objects.filter(beamline=beamline).filter(scheduled_filter).exists():
                info['warning'] = (
                    "Another project is scheduled in this time. "
                    "Proceeding to schedule this beamtime will remove the existing beamtime."
                )
            initial.update(**info)
        except Exception as err:
            logger.exception(err)

        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        obj = self.object

        local_bt = models.Beamtime.objects.filter(beamline=obj.beamline, source_id__isnull=True)
        local_bt.filter(
            Q(start__lt=obj.start) & Q(end__gt=obj.start)).update(**{'end': obj.start})
        local_bt.filter(
            Q(start__lt=obj.end) & Q(end__gt=obj.end)).update(**{'start': obj.end})
        local_bt.filter((
            Q(start__gte=obj.start) & Q(start__lt=obj.end)) | (
            Q(end__lte=obj.end) & Q(end__gt=obj.start)) | (
            Q(start__gte=obj.start) & Q(end__lte=obj.end))).exclude(pk=obj.pk).delete()

        if form.cleaned_data['notify']:
            models.EmailNotification.objects.create(beamtime=self.object)

        return response


class LocalScheduleRecordRequiredMixin(AdminRequiredMixin):
    def test_func(self):
        if not super().test_func():
            return False
        return not bool(self.get_object().source_id)


class BeamtimeEdit(LocalScheduleRecordRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.BeamtimeForm
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
        response = super().form_valid(form)
        obj = self.object

        obj.notifications.filter(sent=False).delete()
        if form.cleaned_data['notify']:
            models.EmailNotification.objects.create(beamtime=obj)

        local_bt = models.Beamtime.objects.filter(beamline=obj.beamline, source_id__isnull=True)
        local_bt.filter(
            Q(start__lt=obj.start) & Q(end__gt=obj.start)).update(**{'end': obj.start})
        local_bt.filter(
            Q(start__lt=obj.end) & Q(end__gt=obj.end)).update(**{'start': obj.end})
        local_bt.filter((
            Q(start__gte=obj.start) & Q(start__lt=obj.end)) | (
            Q(end__lte=obj.end) & Q(end__gt=obj.start)) | (
            Q(start__gte=obj.start) & Q(end__lte=obj.end))).exclude(pk=obj.pk).delete()

        return response


class BeamtimeDelete(LocalScheduleRecordRequiredMixin, SuccessMessageMixin, ModalDeleteView):
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


class SupportDetail(LoginRequiredMixin, detail.DetailView):
    model = models.BeamlineSupport
    template_name = "schedule/support-info.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['current'] = self.request.GET.get('current') == 'True'
        return ctx


class SupportCreate(AdminRequiredMixin, SuccessMessageMixin, ModalCreateView):
    form_class = forms.BeamlineSupportForm
    model = models.BeamlineSupport
    success_url = reverse_lazy('schedule')
    success_message = "Beamline Support has been created"

    def get_initial(self):
        initial = super().get_initial()
        dt = self.request.GET.get('date')
        if dt:
            initial['date'] = datetime.strptime(dt, "%Y-%m-%d")

        return initial


class SupportEdit(AdminRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.BeamlineSupportForm
    model = models.BeamlineSupport
    success_url = reverse_lazy('schedule')
    success_message = "Beamline Support has been updated"


class SupportDelete(AdminRequiredMixin, SuccessMessageMixin, ModalDeleteView):
    model = models.BeamlineSupport
    success_url = reverse_lazy('schedule')
    success_message = "Beamline Support has been deleted"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_action'] = reverse_lazy('support-delete', kwargs={'pk': self.object.pk})
        return context


def split_visits(obj, start, end):
    local_beamtimes = models.Beamtime.objects.filter(
        beamline=obj.beamline, source_id__isnull=True
    )

    originals = local_beamtimes.filter((Q(end__lte=end) & Q(end__gt=start))).filter(start__lt=start)
    for bt in originals:
        clone_info = {f.name: getattr(bt, f.name) for f in bt._meta.fields}
        clone_info.update({'id': None, 'start': start, 'source_id': None})
        clone = models.Beamtime(**clone_info)
        clone.save()
        bt.end = start
        bt.save()

    originals = local_beamtimes.filter((Q(start__lt=end) & Q(start__gte=start))).filter(end__gt=end)
    for bt in originals:
        clone_info = {f.name: getattr(bt, f.name) for f in bt._meta.fields}
        clone_info.update({'id': None, 'end': end, 'source_id': None})
        clone = models.Beamtime(**clone_info)
        clone.save()
        bt.start = end
        bt.save()

    originals = local_beamtimes.filter(start__lt=start).filter(end__gt=end)
    for bt in originals:
        clone1_info = {f.name: getattr(bt, f.name) for f in bt._meta.fields}
        clone1_info.update({'id': None, 'end': end, 'source_id': None})
        clone1 = models.Beamtime(**clone1_info)
        clone1.save()

        clone2_info = {f.name: getattr(bt, f.name) for f in bt._meta.fields}
        clone2_info.update({'id': None, 'start': end, 'source_id': None})
        clone2 = models.Beamtime(**clone2_info)
        clone2.save()

        bt.start = start
        bt.end = end
        bt.save()


class DowntimeCreate(AdminRequiredMixin, SuccessMessageMixin, ModalCreateView):
    form_class = forms.DowntimeForm
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
        response = super().form_valid(form)
        obj = self.object

        split_visits(obj, obj.start, obj.end)
        models.Beamtime.objects.filter(beamline=obj.beamline, source_id__isnull=True).filter(
            (Q(start__gte=obj.start) & Q(end__lte=obj.end))).update(cancelled=True)

        return response


class DowntimeEdit(LocalScheduleRecordRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.DowntimeForm
    model = models.Downtime
    success_url = reverse_lazy('schedule')
    success_message = "Downtime has been updated"

    def form_valid(self, form):
        fv = super().form_valid(form)
        obj = form.instance

        if form.data.get('submit') == 'Delete':
            models.Beamtime.objects.filter(
                beamline=obj.beamline, source_id__isnull=True, start__gte=obj.start, end__lte=obj.end
            ).update(cancelled=False)
            obj.delete()
            self.success_message = "Downtime has been deleted"
        else:
            if obj.start < form.initial['start']:
                start = obj.start
                end = form.initial['start']

                split_visits(obj, start, end)
                models.Beamtime.objects.filter(beamline=obj.beamline, source_id__isnull=True).filter(
                    (Q(start__gte=start) & Q(end__lte=end))).update(cancelled=True)
            if obj.end > form.initial['end']:
                start = form.initial['end']
                end = obj.end

                split_visits(obj, start, end)
                models.Beamtime.objects.filter(beamline=obj.beamline, source_id__isnull=True).filter(
                    (Q(start__gte=start) & Q(end__lte=end))).update(cancelled=True)

        return fv


class EmailNotificationList(AdminRequiredMixin, ListViewMixin, ItemListView):
    model = models.EmailNotification
    list_filters = ['send_time', 'sent']
    list_columns = ['id', 'sent', 'unsendable', 'send_time', 'beamtime__start', 'beamtime__project__name', 'email_subject']
    list_search = ['email_subject', 'email_body']
    link_url = 'email-edit'
    ordering = ['-send_time']
    ordering_proxies = {}
    list_transforms = {}
    show_project = False
    link_attr = 'data-modal-url'

    def get_queryset(self):
        return super().get_queryset()


class EmailNotificationEdit(AdminRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.EmailNotificationForm
    model = models.EmailNotification
    success_url = reverse_lazy('schedule')
    success_message = "Email Notification has been updated"

    def get_initial(self):
        initial = super().get_initial()
        initial['recipients'] = '; '.join(self.object.recipient_list())
        if self.object.unsendable():
            initial['warning'] = "This email cannot be sent. Either the send time has already passed, the beamtime has been cancelled, or there are no recipients."

        return initial