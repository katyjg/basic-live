from datetime import datetime

from crisp_modals.views import ModalCreateView, ModalUpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.http import Http404
from django.template.defaultfilters import linebreaksbr
from django.utils import timezone
from django.utils.text import slugify
from django.views.generic import edit, detail
from itemlist.views import ItemListView

from basiclive.core.lims.views import ListViewMixin
from basiclive.utils import filters
from basiclive.utils.mixins import AdminRequiredMixin
from . import forms, models
from ...utils.misc import natural_duration


def format_contact(val, record):
    return val and record.session.project or ""


def format_comments(val, record):
    text = ''.join([
        f'<div class="small">{paragraph}</div>' for paragraph in val.split('\n') if paragraph
    ])
    time_text = natural_duration(record.created)
    staff_text = "" if not record.staff else f" by <strong>{record.staff}</strong>&nbsp;"
    return (
        f"{text}<br/>"
        f"<div class='small text-end text-muted'>Created{staff_text} for <span>{record.project.name.upper()}</span>"
        f"&nbsp; <span>{time_text} ago</span></div>"
    )


def format_kind(val, record):
    if record.kind == models.SupportRecord.TYPE.problem:
        return (
            f"<span class='badge badge-md text-danger-emphasis bg-danger-subtle'>{record.area} | "
            f"<strong>{record.get_kind_display()}</strong></span>"
        )
    elif record.kind == models.SupportRecord.TYPE.info:
        return (
            f"<span class='badge badge-md text-info-emphasis bg-info-subtle'>{record.area} | "
            f"<strong>{record.get_kind_display()}</strong></span>"
        )
    return ""


def format_hours(val, record):
    delta = timezone.timedelta(hours=val)
    return natural_duration(delta)


def format_created(val, args):
    return datetime.strftime(timezone.localtime(val), '%b %d, %Y %H:%M ')


class SupportAreaList(ListViewMixin, ItemListView):
    model = models.SupportArea
    list_filters = ['user_feedback']
    list_columns = ['name', 'label', 'user_feedback']
    list_search = ['name', 'label']
    link_field = 'name'
    show_project = False
    ordering = ['name']
    tool_template = 'crm/tools-support.html'
    link_url = 'supportarea-edit'
    link_attr = 'data-modal-url'


class SupportAreaCreate(AdminRequiredMixin, SuccessMessageMixin, ModalCreateView):
    form_class = forms.SupportAreaForm
    model = models.SupportArea
    success_message = "Support area has been created"


class SupportAreaEdit(AdminRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.SupportAreaForm
    model = models.SupportArea
    success_message = "Support area has been updated"


class FeedbackList(ListViewMixin, ItemListView):
    model = models.Feedback
    list_filters = [
        'session__beamline',
        'created',
        filters.YearFilter('created', reverse=True),
        filters.MonthFilter('created'),
        filters.QuarterFilter('created'),
        'session__project__designation',
        'session__project__kind',
    ]
    list_columns = ['created', 'session__beamline__acronym', 'comments', 'contact']
    list_transforms = {'contact': format_contact}
    list_search = ['session__project__name', 'comments']
    ordering = ['-created']
    tool_template = 'crm/tools-support.html'
    show_project = False
    link_url = 'user-feedback-detail'
    link_attr = 'data-modal-url'


class FeedbackDetail(AdminRequiredMixin, detail.DetailView):
    model = models.Feedback
    template_name = "crm/feedback.html"


class FeedbackCreate(LoginRequiredMixin, UserPassesTestMixin, edit.CreateView):
    form_class = forms.FeedbackForm
    template_name = "crm/forms/survey.html"
    model = models.Feedback
    success_url = '/'
    success_message = "User Feedback has been submitted"

    def test_func(self):
        project_name = self.kwargs.get('project')
        session_id = self.kwargs.get('session')

        flt = (Q(pi_id=self.request.user.pk) | Q(members__pk=self.request.user.pk)) & Q(name=project_name)
        if not self.request.user.is_authenticated:
            return False
        elif not models.Session.objects.filter(project__name=project_name, id=session_id).exists():
            return False
        elif self.request.user.is_superuser:
            return True
        elif models.Project.objects.filter(flt).exists():
            return True
        return False

    def get_initial(self):
        initial = super().get_initial()
        try:
            project_name = self.kwargs.get('project')
            session_id = self.kwargs.get('session')
            initial['session'] = models.Session.objects.get(project__name=project_name, id=session_id)
        except (models.Session.DoesNotExist, ValueError):
            raise Http404

        return initial

    def form_valid(self, form):
        response = super().form_valid(form)

        to_create = []

        for area in models.SupportArea.objects.filter(user_feedback=True):
            scale = area.scale
            key = slugify(area.name)
            if form.cleaned_data.get(key):
                rating = int(form.cleaned_data.get(key)[0])
                label = scale.get_label(rating)
                to_create.append(
                    models.AreaFeedback(
                        feedback=self.object,
                        area=area,
                        label=label,
                        rating=rating
                    )
                )

        models.AreaFeedback.objects.bulk_create(to_create)
        return response


class SupportEntryList(AdminRequiredMixin, ListViewMixin, ItemListView):
    model = models.SupportRecord
    list_filters = [
        'beamline',
        filters.YearFilter('created', reverse=True),
        filters.MonthFilter('created'),
        'project__kind',
        'kind',
        'area'
    ]
    list_columns = ['beamline', 'kind', 'lost_time', 'comments']
    list_transforms = {
        'comments': format_comments,
        'created': format_created,
        'lost_time': format_hours,
        'kind': format_kind,
    }
    list_styles = {
        'beamline': 'text-nowrap'
    }
    list_search = ['beamline__acronym', 'project__name', 'comments', 'staff__name', 'staff__first_name', 'staff__last_name', 'staff__username']
    ordering = ['-created']
    tool_template = 'crm/tools-support.html'
    link_url = 'supportrecord-edit'
    link_field = 'beamline'
    show_project = False
    link_attr = 'data-modal-url'


class SupportEntryCreate(AdminRequiredMixin, SuccessMessageMixin, ModalCreateView):
    form_class = forms.SupportEntryForm
    model = models.SupportRecord
    success_message = "Support record has been created"

    def get_initial(self):
        initial = super().get_initial()
        project_param = self.request.GET.get('project')
        if project_param:
            initial['project'] = models.Project.objects.filter(name=project_param).first()
        initial['beamline'] = models.Beamline.objects.filter(acronym=self.request.GET.get('beamline')).first()
        if self.request.user and getattr(self.request.user, 'is_staff', False):
            initial['staff'] = self.request.user
        return initial


class SupportEntryEdit(AdminRequiredMixin, SuccessMessageMixin, ModalUpdateView):
    form_class = forms.SupportEntryForm
    model = models.SupportRecord
    success_message = "Support record has been updated"
