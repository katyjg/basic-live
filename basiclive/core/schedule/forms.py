from django import forms
from django.urls import reverse_lazy
from django.utils.translation import ugettext_lazy as _

from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Div, Field, Layout, HTML

from basiclive.core.lims.models import Project
from basiclive.core.lims.forms import BodyHelper, FooterHelper
from .models import Beamtime, BeamlineSupport, Downtime, EmailNotification


class BeamtimeForm(forms.ModelForm):

    notify = forms.BooleanField(label=_("Schedule email notification"), widget=forms.CheckboxInput(), required=False)

    class Meta:
        model = Beamtime
        fields = ['project', 'beamline', 'start', 'end', 'comments', 'access', 'notify']
        widgets = {
            'comments': forms.Textarea(attrs={"cols": 40, "rows": 7}),
            'beamline': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        errors = Div()
        if self.initial.get('warning'):
            errors = Div(
                Div(
                    HTML(self.initial.get('warning')),
                    css_class="card-header"
                ),
                css_class="card bg-danger text-white"
            )

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        if self.instance.pk:
            self.body.title = u"Edit Beamtime"
            self.body.form_action = reverse_lazy('beamtime-edit', kwargs={'pk': self.instance.pk})
        else:
            self.body.title = u"New Beamtime"
            self.body.form_action = reverse_lazy('new-beamtime')
        self.body.layout = Layout(
            errors,
            Div(
                Div('project', css_class="col-12"),
                Div('beamline', css_class="col-12"),
                css_class="row"
            ),
            Div(
                Div(Field('start'), css_class="col-6"),
                Div(Field('end'), css_class="col-6"),
                css_class="row"
            ),
            Div(
                Div(Field('access', css_class="select"), css_class="col-6"),
                Div(Field('notify'), css_class="col-6 px-4 pt-4"),
                css_class="row"
            ),
            Div(
                Div('comments', css_class="col-12"),
                css_class="row"
            ),
        )
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )


class BeamlineSupportForm(forms.ModelForm):

    staff = forms.ModelChoiceField(queryset=Project.objects.filter(kind__name="Staff"))

    class Meta:
        model = BeamlineSupport
        fields = ['staff', 'date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        if self.instance.pk:
            self.body.title = u"Edit Beamline Support"
            self.body.form_action = reverse_lazy('support-edit', kwargs={'pk': self.instance.pk})
        else:
            self.body.title = u"New Beamline Support"
            self.body.form_action = reverse_lazy('new-support')
        self.body.layout = Layout(
            Div(
                Div('staff', css_class="col-12"),
                Div(Field('date', readonly=True), css_class="col-12"),
                css_class="row"
            )
        )
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )


class DowntimeForm(forms.ModelForm):

    class Meta:
        model = Downtime
        fields = ['scope', 'beamline', 'start', 'end', 'comments']
        widgets = {
            'comments': forms.Textarea(attrs={"cols": 40, "rows": 7}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        if self.instance.pk:
            self.body.title = u"Edit Downtime"
            self.body.form_action = reverse_lazy('downtime-edit', kwargs={'pk': self.instance.pk})
            delete_btn = StrictButton('Delete', type='delete', value='Delete', css_class="btn btn-danger pull-left")
        else:
            self.body.title = u"Mark Downtime"
            self.body.form_action = reverse_lazy('new-downtime')
            delete_btn = Div()
        self.body.layout = Layout(
            Div(
                Div('scope', css_class="col-12"),
                css_class="row"
            ),
            Div(
                Div(Field('start'), css_class="col-6"),
                Div(Field('end'), css_class="col-6"),
                css_class="row"
            ),
            Div(
                Div('beamline', css_class="col-12"),
                Div('comments', css_class="col-12"),
                css_class="row"
            ),
        )
        self.footer.layout = Layout(
            delete_btn,
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )


class EmailNotificationForm(forms.ModelForm):
    recipients = forms.CharField(required=False)

    class Meta:
        model = EmailNotification
        fields = ['beamtime', 'send_time', 'email_subject', 'email_body', 'recipients']
        widgets = {
            'email_body': forms.Textarea(attrs={"cols": 42, "rows": 10}),
            'beamtime': forms.HiddenInput()
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        errors = Div()
        if self.initial.get('warning'):
            errors = Div(
                Div(
                    HTML(self.initial.get('warning')),
                    css_class="card-header"
                ),
                css_class="card bg-danger text-white"
            )

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Edit Email Notification"
        self.body.form_action = reverse_lazy('email-edit', kwargs={'pk': self.instance.pk})

        self.body.layout = Layout(
            errors,
            Div(
                Div(Field('recipients', readonly=True), css_class="col-12"),
                Div('beamtime', css_class="col-12"),
                Div('send_time', css_class="col-12"),
                css_class="row"
            ),
            Div(
                Div('email_subject', css_class="col-12"),
                Div('email_body', css_class="col-12"),
                css_class="row"
            ),
        )
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )
