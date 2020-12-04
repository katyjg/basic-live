from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.urls import reverse_lazy

from basiclive.core.lims.forms import BodyHelper, FooterHelper
from basiclive.core.acl.models import AccessList


class AccessForm(forms.ModelForm):

    class Meta:
        model = AccessList
        fields = ('users',)

    def __init__(self, *args, **kwargs):
        super(AccessForm, self).__init__(*args, **kwargs)
        self.fields['users'].label = "Users on {}".format(self.instance)
        self.fields['users'].queryset = self.fields['users'].queryset.order_by('name')

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Edit Remote Access List"
        self.body.form_action = reverse_lazy('access-edit', kwargs={'address': self.instance.address})
        self.body.layout = Layout(
            Div(
                Div(
                    Field('users', css_class="select"),
                    css_class="col-12"
                ),
                css_class="row"
            ),
            Div(
                Div(
                    HTML("It may take a few minutes for changes to be updated on the server."),
                    css_class="col-12"
                ),
                css_class="row"
            )
        )
        self.footer.layout = Layout(
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )
