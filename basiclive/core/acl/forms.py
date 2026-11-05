from crisp_modals.forms import Button, FullWidth, ModalModelForm, Row
from crispy_forms.layout import HTML, Field, Layout
from django.urls import reverse_lazy

from basiclive.core.acl.models import AccessList


class AccessForm(ModalModelForm):

    class Meta:
        model = AccessList
        fields = ('users',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['users'].label = f"Projects on {self.instance}"
        self.fields['users'].queryset = self.fields['users'].queryset.order_by('name')

        self.body.title = "Edit Remote Access List"
        self.body.form_action = reverse_lazy('access-edit', kwargs={'pk': self.instance.pk})
        self.body.layout = Layout(
            Row(
                FullWidth(Field('users', css_class="select")),
            ),
            Row(
                FullWidth(HTML("It may take a few minutes for changes to be updated on the server.")),
            )
        )
        self.footer.set_buttons(
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )
