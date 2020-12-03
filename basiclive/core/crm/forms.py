from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.urls import reverse_lazy
from django.utils.text import slugify

from .models import SupportRecord, SupportArea, Feedback, LikertScale
from basiclive.core.lims.models import Project
from basiclive.core.lims.forms import BodyHelper, FooterHelper


class SupportAreaForm(forms.ModelForm):

    class Meta:
        model = SupportArea
        fields = ['name', 'user_feedback', 'external', 'scale']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        if self.instance.pk:
            self.body.title = u"Edit Support Area"
            self.body.form_action = reverse_lazy('supportarea-edit', kwargs={'pk': self.instance.pk})
        else:
            self.body.title = u"New Support Area"
            self.body.form_action = reverse_lazy('new-supportarea')

        self.body.layout = Layout(
            Div(
                Div('name', css_class="col-12"),
                Div(Div('user_feedback', css_class="mt-3 ml-3 pl-1"), css_class="col-6"),
                Div('scale', css_class="col-6"),
                Div(Div('external', css_class="mt-3 ml-3 pl-1"), css_class="col-12"),
                css_class="row"
            ),
        )
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )


class LikertTable(Div):
    template = "crm/forms/likert-table.html"

    def __init__(self, *fields, **kwargs):
        super().__init__(*fields, **kwargs)
        self.options = kwargs.get('options')


class LikertEntry(Field):
    template = "crm/forms/likert-entry.html"


class FeedbackForm(forms.ModelForm):

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

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"User Experience Survey"
        self.body.form_action = reverse_lazy('session-feedback', kwargs={'key': self.initial['session'].feedback_key()})

        likert_tables = []
        area_pks = SupportArea.objects.filter(user_feedback=True).values_list('scale__pk', flat=True)
        for scale in LikertScale.objects.filter(pk__in=area_pks):
            likert_tables.append(HTML(scale.statement))
            likert_table = LikertTable(options=scale.choices())
            for area in SupportArea.objects.filter(user_feedback=True, scale=scale):
                name = slugify(area.name)
                self.fields[name] = forms.MultipleChoiceField(choices=scale.choices(), label=area.name, initial=0)
                likert_table.append(LikertEntry(slugify(name)))
            likert_tables.append(likert_table)
            likert_tables.append(HTML("""<br/>"""))

        self.body.layout = Layout(
            'session',
            HTML("""<p class="text-large text-condensed">
                    Help us improve your next visit or session by letting us know how we did this time.</p>"""),
            *likert_tables,
            Div(
                Div('comments', css_class="col-12"),
                Div('contact', css_class="mx-3 px-1 col-12"),
                css_class="row"
            ),
        )
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )


class SupportEntryForm(forms.ModelForm):
    staff = forms.ModelChoiceField(queryset=Project.objects.filter(kind__name="Staff"))

    class Meta:
        model = SupportRecord
        fields = ['kind', 'areas', 'staff', 'project', 'beamline', 'comments', 'staff_comments', 'lost_time']
        widgets = {
            'comments': forms.Textarea(attrs={
                "cols": 40, "rows": 7, "placeholder": 'Question/Concern from User:\nMy Response/Action Taken:'}),
            'staff_comments': forms.Textarea(attrs={'cols': 40, 'rows': 7})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        if self.instance.pk:
            self.body.title = u"Edit Record of User Support"
            self.body.form_action = reverse_lazy('supportrecord-edit', kwargs={'pk': self.instance.pk})
        else:
            self.body.title = u"New Record of User Support"
            self.body.form_action = reverse_lazy('new-supportrecord')
            self.fields['staff_comments'].widget = forms.HiddenInput()

        self.body.layout = Layout(
            Div(
                Div('staff', css_class='col-4'),
                Div('beamline', css_class="col-4"),
                Div('project', css_class='col-4'),
                css_class="row"
            ),
            Div(
                Div('kind', css_class="col-6"),
                Div('lost_time', css_class="col-6"),
                Div(Field('areas', css_class="select"), css_class="col-12"),
                css_class="row"
            ),
            Div(
                Div('comments', css_class="col-12"),
                Div('staff_comments', css_class="col-12"),
                css_class="row"
            ),
        )
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )
