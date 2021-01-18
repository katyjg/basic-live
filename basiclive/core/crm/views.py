from datetime import datetime

from django.conf import settings
from django.contrib.messages.views import SuccessMessageMixin
from django.http import Http404
from django.template.defaultfilters import linebreaksbr
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.text import slugify
from django.views.generic import edit, detail
from itemlist.views import ItemListView

from basiclive.core.lims.views import ListViewMixin
from basiclive.utils import filters
from basiclive.utils.encrypt import decrypt
from basiclive.utils.mixins import AsyncFormMixin, AdminRequiredMixin, PlotViewMixin
from . import forms, models, stats

if settings.LIMS_USE_SCHEDULE:
    from basiclive.core.schedule.models import BeamlineSupport


def format_contact(val, record):
    return val and record.session.project or ""


def format_comments(val, args):
    return linebreaksbr(val)


def format_areas(val, record):
    return '<br/>'.join(["<span class='badge badge-info'>{}</span>".format(a.name) for a in record.areas.all()])


def format_created(val, args):
    return datetime.strftime(timezone.localtime(val), '%b %d, %Y %H:%M ')


class SupportAreaList(ListViewMixin, ItemListView):
    model = models.SupportArea
    list_filters = ['user_feedback']
    list_columns = ['name', 'user_feedback']
    list_search = ['name']
    link_field = 'name'
    show_project = False
    ordering = ['name']
    tool_template = 'crm/tools-support.html'
    link_url = 'supportarea-edit'
    link_attr = 'data-form-link'


class SupportAreaCreate(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.CreateView):
    form_class = forms.SupportAreaForm
    template_name = "modal/form.html"
    model = models.SupportArea
    success_url = reverse_lazy('supportarea-list')
    success_message = "Support area has been created"


class SupportAreaEdit(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.SupportAreaForm
    template_name = "modal/form.html"
    model = models.SupportArea
    success_url = reverse_lazy('supportarea-list')
    success_message = "Support area has been updated"


class FeedbackList(ListViewMixin, ItemListView):
    model = models.Feedback
    list_filters = [
        'session__beamline',
        'created',
        filters.YearFilterFactory('created', reverse=True),
        filters.MonthFilterFactory('created'),
        filters.QuarterFilterFactory('created'),
        'session__project__designation',
        'session__project__kind',
    ]
    list_columns = ['created', 'session__beamline__acronym', 'comments', 'contact']
    list_transforms = {'contact': format_contact}
    list_search = ['session__project__username', 'comments']
    ordering = ['-created']
    tool_template = 'crm/tools-support.html'
    show_project = False
    link_url = 'user-feedback-detail'
    link_attr = 'data-link'
    plot_url = reverse_lazy("user-feedback-stats")


class FeedbackDetail(AdminRequiredMixin, detail.DetailView):
    model = models.Feedback
    template_name = "crm/feedback.html"


class FeedbackCreate(SuccessMessageMixin, edit.CreateView):
    form_class = forms.FeedbackForm
    template_name = "crm/forms/survey.html"
    model = models.Feedback
    success_url = reverse_lazy('dashboard')
    success_message = "User Feedback has been submitted"

    def get_initial(self):
        initial = super().get_initial()
        try:
            username, name = decrypt(self.kwargs.get('key')).split(':')
            initial['session'] = models.Session.objects.get(project__username=username, name=name)
        except models.Session.DoesNotExist:
            raise Http404

        return initial

    def form_valid(self, form):
        response = super().form_valid(form)

        to_create = []

        for area in models.SupportArea.objects.filter(user_feedback=True):
            if form.cleaned_data.get(slugify(area.name)):
                to_create.append(models.AreaFeedback(feedback=self.object, area=area,
                                                     rating=form.cleaned_data.get(slugify(area.name))[0]))

        models.AreaFeedback.objects.bulk_create(to_create)
        return response


class SupportEntryList(ListViewMixin, ItemListView):
    model = models.SupportRecord
    list_filters = [
        'beamline',
        'created',
        filters.YearFilterFactory('created', reverse=True),
        filters.MonthFilterFactory('created'),
        'project__designation',
        'project__kind',
        'kind',
        'areas'
    ]
    list_columns = ['beamline', 'staff', 'created', 'kind', 'comments', 'area', 'lost_time']
    list_transforms = {'comments': format_comments, 'area': format_areas, 'created': format_created}
    list_search = ['beamline__acronym', 'project__username', 'comments']
    ordering = ['-created']
    tool_template = 'crm/tools-support.html'
    link_url = 'supportrecord-edit'
    link_field = 'beamline'
    link_attr = 'data-form-link'
    plot_url = reverse_lazy("supportrecord-stats")


class SupportEntryStats(PlotViewMixin, SupportEntryList):
    date_field = 'created'
    list_url = reverse_lazy("supportrecord-list")

    def get_metrics(self):
        return stats.supportrecord_stats(self.get_queryset(), self.get_active_filters())


class FeedbackStats(PlotViewMixin, FeedbackList):
    date_field = 'created'
    list_url = reverse_lazy("user-feedback-list")

    def get_metrics(self):
        return stats.feedback_stats(self.get_queryset(), self.get_active_filters())


class SupportEntryCreate(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.CreateView):
    form_class = forms.SupportEntryForm
    template_name = "modal/form.html"
    model = models.SupportRecord
    success_url = reverse_lazy('supportrecord-list')
    success_message = "Support record has been created"

    def get_initial(self):
        initial = super().get_initial()
        initial['project'] = models.Project.objects.filter(username=self.request.GET.get('project')).first()
        initial['beamline'] = models.Beamline.objects.filter(acronym=self.request.GET.get('beamline')).first()
        if settings.LIMS_USE_SCHEDULE:
            support = BeamlineSupport.objects.filter(date=timezone.now().date()).first()
            initial['staff'] = support and support.staff or None
        return initial


class SupportEntryEdit(AdminRequiredMixin, SuccessMessageMixin, AsyncFormMixin, edit.UpdateView):
    form_class = forms.SupportEntryForm
    template_name = "modal/form.html"
    model = models.SupportRecord
    success_url = reverse_lazy('supportrecord-list')
    success_message = "Support record has been updated"
