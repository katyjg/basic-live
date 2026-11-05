from crisp_modals.forms import (
    Button,
    FullWidth,
    HalfWidth,
    ModalModelForm,
    Row,
    ThirdWidth, ThreeQuarterWidth, QuarterWidth,
)
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.contrib.auth import get_user_model
from django.urls import reverse_lazy
from django.utils.text import slugify

from django.utils.translation import gettext_lazy as _

from basiclive.core.lims.models import Beamline
from .models import SupportRecord, SupportArea, Feedback, LikertScale

User = get_user_model()


class SupportAreaForm(ModalModelForm):

    class Meta:
        model = SupportArea
        fields = ['name', 'label', 'user_feedback', 'external', 'scale']
        widgets = {
            'label': forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "label": _(
                "Questionnaire prompt or statement displayed in user experience surveys. "
                "Falls back to name if blank."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.body.layout = Layout(
            Row(
                ThreeQuarterWidth('name'), QuarterWidth('scale'),
                FullWidth('label'),
                FullWidth('user_feedback'),
                FullWidth('external'),
            ),
        )
        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )


class LikertTable(Div):
    template = "crm/forms/likert-table.html"

    def __init__(self, *fields, **kwargs):
        super().__init__(*fields, **kwargs)
        self.options = kwargs.get('options')


class LikertEntry(Field):
    template = "crm/forms/likert-entry.html"


class FeedbackForm(ModalModelForm):

    class Meta:
        model = Feedback
        fields = ['comments', 'contact', 'session']
        widgets = {
            'session': forms.HiddenInput(),
            'comments': forms.Textarea(attrs={"cols": 40, "rows": 7})
        }
        labels = {
            'contact': 'I would like to be contacted about my recent experience.',
            'comments': 'Provide comments to explain or give context to the ratings you selected.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.body.title = "User Experience Survey"
        likert_tables = []
        area_pks = SupportArea.objects.filter(user_feedback=True).values_list('scale__pk', flat=True)
        for scale in LikertScale.objects.filter(pk__in=area_pks):
            likert_tables.append(HTML(scale.statement))
            likert_table = LikertTable(options=scale.choices())
            for area in SupportArea.objects.filter(user_feedback=True, scale=scale):
                name = slugify(area.name)
                self.fields[name] = forms.MultipleChoiceField(choices=scale.choices(), label=area.display_label, initial=0)
                likert_table.append(LikertEntry(slugify(name)))
            likert_tables.append(likert_table)
            likert_tables.append(HTML("""<br/>"""))

        self.body.layout = Layout(
            'session',
            HTML("""<p class="text-large text-condensed">
                    Help us improve your next visit or session by letting us know how we did this time.</p>"""),
            *likert_tables,
            Row(
                FullWidth('comments'),
                FullWidth('contact', style="mx-3 px-1"),
            ),
        )
        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )


class SupportEntryForm(ModalModelForm):
    staff = forms.ModelChoiceField(
        queryset=User.objects.filter(is_staff=True, is_active=True).order_by('first_name', 'last_name', 'username')
    )

    class Meta:
        model = SupportRecord
        fields = ['kind', 'area', 'staff', 'project', 'beamline', 'comments', 'staff_comments', 'lost_time']
        widgets = {
            'comments': forms.Textarea(attrs={
                "rows": 7, "placeholder": 'Question/Concern from User:\nMy Response/Action Taken:'}),
            'staff_comments': forms.Textarea(attrs={'rows': 3})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            self.body.title = "Edit Record of User Support"
            self.body.form_action = reverse_lazy('supportrecord-edit', kwargs={'pk': self.instance.pk})
        else:
            self.body.title = "New Record of User Support"
            self.body.form_action = reverse_lazy('new-supportrecord')
            self.fields['staff_comments'].widget = forms.HiddenInput()

        self.fields['beamline'].queryset = Beamline.objects.filter(simulated=False, active=True)

        self.body.layout = Layout(
            Row(
                ThirdWidth('staff'),
                ThirdWidth('beamline'),
                ThirdWidth('project'),
            ),
            Row(
                ThirdWidth('kind'),
                ThirdWidth('area'),
                ThirdWidth('lost_time'),
            ),
            Row(
                FullWidth('comments'),
                FullWidth('staff_comments'),
            ),
        )
        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )

    def clean(self):
        kind = self.cleaned_data.get('kind')
        lost_time = self.cleaned_data.get('lost_time')
        if kind == 'problem' and lost_time <= 0:
            raise forms.ValidationError("Please enter the amount of time lost due to this problem.")
        if kind == 'info' and lost_time > 0:
            raise forms.ValidationError("If time was lost, then Kind should be 'Problem'")
        return self.cleaned_data
