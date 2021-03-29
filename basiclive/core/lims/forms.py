import re
import fastjsonschema
from collections import OrderedDict

from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Layout
from django.utils.translation import ugettext as _
from django import forms
from django.conf import settings
from django.db.models import Q
from django.urls import reverse_lazy

from .models import Project, Shipment, Automounter, Sample, ComponentType, Container, Group, ContainerLocation, ContainerType
from .models import Guide, ProjectType, SSHKey, RequestType, Request, REQUEST_SPEC_SCHEMA


class BodyHelper(FormHelper):
    def __init__(self, form):
        super().__init__(form)
        self.form_tag = False
        self.use_custom_control = True
        self.form_show_errors = False


class FooterHelper(FormHelper):
    def __init__(self, form):
        super().__init__(form)
        self.form_tag = False
        self.disable_csrf = True
        self.form_show_errors = False


disabled_widget = forms.HiddenInput(attrs={'readonly': True})


class HiddenArea(forms.HiddenInput):
    template_name = 'django/forms/widgets/textarea.html'


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ('first_name', 'last_name', 'email', 'contact_person', 'contact_email', 'contact_phone',
                  'carrier', 'account_number', 'organisation', 'department', 'address', 'city', 'province',
                  'postal_code', 'country', 'kind', 'alias', 'designation')

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super(ProjectForm, self).__init__(*args, **kwargs)
        pk = self.instance.pk

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        if pk:
            self.body.title = _("Edit Profile")
            self.body.form_action = reverse_lazy('edit-profile', kwargs={'username': self.instance.username})
        else:
            self.body.title = _("Create New Profile")
            self.body.form_action = reverse_lazy('new-project')

        if not self.user.is_superuser:
            for f in ['kind', 'alias', 'first_name', 'last_name', 'email', 'designation']:
                self.fields[f].widget.attrs['readonly'] = True
            self.fields['designation'].widget = forms.MultipleHiddenInput()

        self.body.layout = Layout(
            Div(
                Div('first_name', css_class='col-6'),
                Div('last_name', css_class='col-6'),
                Div('email', css_class='col-{}'.format(self.user.is_superuser and '6' or '12')),
                self.user.is_superuser and Div(Field('designation', css_class='select'), css_class='col-6') or Div('designation'),
                css_class='form-row'
            ),
            Div(
                Div(Field('kind', css_class='select'), css_class='col-6'),
                Div('alias', css_class='col-6'),
                Div('contact_person', css_class='col-12'),
                css_class="form-row"
            ),
            Div(
                Div('contact_email', css_class='col-6'),
                Div(
                    Field(
                        'contact_phone', pattern="(\+\d{1,3}-)?\d{3}-\d{3}-\d{4}( x\d+)?$",
                        placeholder="[+9-]999-999-9999[ x9999]"
                    ),
                    css_class='col-6'
                ),
                css_class="form-row"
            ),
            Div(
                Div(Field('carrier', css_class="select"), css_class='col-6'),
                Div('account_number', css_class='col-6'),
                css_class="form-row"
            ),
            Div(
                Div('organisation', css_class='col-12'),
                css_class="form-row"
            ),
            Div(
                Div('department', css_class='col-12'),
                css_class="form-row"
            ),
            Div(
                Div('address', css_class='col-12'),
                css_class="form-row"
            ),
            Div(
                Div('city', css_class='col-6'),
                Div('province', css_class='col-6'),
                css_class="form-row"
            ),
            Div(
                Div('country', css_class='col-6'),
                Div('postal_code', css_class='col-6'),
                css_class="form-row"
            )
        )
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='submit', css_class='btn btn-primary'),
        )


class NewProjectForm(forms.ModelForm):
    password = forms.CharField(required=False, help_text=_('A password will be auto-generated for this account'))

    class Meta:
        model = Project
        fields = ('first_name', 'last_name', 'email', 'contact_person', 'contact_email', 'contact_phone', 'username',
                  'kind', 'alias', 'designation')

    def __init__(self, *args, **kwargs):
        super(NewProjectForm, self).__init__(*args, **kwargs)

        if getattr(settings, 'LDAP_SEND_EMAILS', False):
            self.fields['password'].help_text += _(' and sent to staff once this form is submitted')
        self.fields['kind'].initial = ProjectType.objects.first()
        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)

        self.body.title = _("Create New User Account")
        self.body.form_action = reverse_lazy('new-project')
        self.footer.layout = Layout()
        self.body.layout = Layout(
            Div(
                Div('username', css_class='col-6'),
                Div(Field('password', disabled=True), css_class="col-6"),
                css_class="form-row"
            ),
            Div(
                Div('first_name', css_class='col-6'),
                Div('last_name', css_class='col-6'),
                Div('email', css_class='col-6'),
                Div(Field('designation', css_class='select'), css_class='col-6'),
                css_class="form-row"
            ),
            Div(
                Div(Field('kind', css_class="select"), css_class='col-6'),
                Div('alias', css_class='col-6'),
                Div('contact_person', css_class='col-12'),
                css_class="form-row"
            ),
            Div(
                Div('contact_email', css_class='col-6'),
                Div('contact_phone', css_class='col-6'),
                css_class="form-row"
            )
        )
        self.footer.layout = Layout(
            StrictButton('Save', type='submit', name="submit", value='submit', css_class='btn btn-primary'),
        )


class RequestTypeForm(forms.ModelForm):
    parameter = forms.CharField(max_length=32, required=False, label=_("Field*"))
    required = forms.ChoiceField(choices=((False, 'No'), (True, 'Yes')), required=False)
    label = forms.CharField(max_length=64, required=False)
    kind = forms.ChoiceField(required=False)
    choices = forms.CharField(max_length=512, required=False)

    class Meta:
        model = RequestType
        fields = ('name', 'description', 'spec', 'edit_template', 'view_template')
        widgets = {
            'description': forms.Textarea(attrs={'rows': "1"}),
            'spec': disabled_widget
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk

        properties = REQUEST_SPEC_SCHEMA['definitions']['field']['properties']
        self.repeated_fields = ['parameter', 'required', 'label', 'kind', 'choices']
        self.repeated_data = {}
        for f in self.repeated_fields:
            info = properties.get(f == 'kind' and 'type' or f, {})
            if info.get('enum'): self.fields[f].choices = ((c, c.title()) for c in info['enum'])
            if info.get('description'):
                self.fields[f].widget.attrs['label'] = info['description']
                self.fields[f].label = info['description']
            self.fields['{}_set'.format(f)] = forms.CharField(required=False)
        if pk:
            spec = self.instance.spec
            parameters = spec.keys()
            self.repeated_data['parameter_set'] = [param for param in parameters]
            self.repeated_data['kind_set'] = [spec[param]['type'] for param in parameters]
            self.repeated_data['label_set'] = [spec[param]['label'] for param in parameters]
            self.repeated_data['choices_set'] = [spec[param].get('choices') and ', '.join(c[0] for c in spec[param]['choices']) or '' for param in parameters]
            self.repeated_data['required_set'] = [str(spec[param]['required']) for param in parameters]

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)

        if pk:
            self.body.title = u"Edit Request Type"
            self.body.form_action = reverse_lazy('requesttype-edit', kwargs={'pk': pk})
        else:
            self.body.title = u"Create New Request Type"
            self.body.form_action = reverse_lazy('new-requesttype')

        self.body.layout = Layout(
            self.help_text(),
            Div(
                'spec',
                Div('name', css_class='col-4'),
                Div('edit_template', css_class='col-4'),
                Div('view_template', css_class='col-4'),
                Div('description', css_class='col-12'),
                css_class="form-row"
            ),
            Div(
                Div(
                    Div(
                        Div(
                            Div(Field('parameter'), css_class="col-2"),
                            Div(Field('kind', css_class="select-alt", data_repeat_enable="true"), css_class="col-2"),
                            Div(Field('label'), css_class="col-3"),
                            Div(Field('choices'), css_class="col-3"),
                            Div(Field('required', css_class="select-alt", data_repeat_enable="true"), css_class="col-1"),
                            Div(
                                Div(
                                    HTML('<label>&nbsp;</label>'),
                                    Div(
                                        StrictButton(
                                            '<i class="ti ti-minus"></i>',
                                            css_class="btn btn-warning float-right safe-remove"
                                        ),
                                    ),
                                    css_class="form-group"
                                ),
                                css_class="col-1"
                            ),
                            css_class="repeat-row template row"
                        ),
                        css_class="col-12 repeat-group repeat-container"
                    ),
                    Div(
                        StrictButton(
                            "<i class='ti ti-plus'></i> Add Parameter", type="button",
                            css_class='btn btn-sm btn-success add'
                        ),
                        css_class="col-12 mt-2"
                    ),
                    css_class="row repeat-wrapper"
                ),
                css_class='repeat'
            ),
        )

        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )

    def help_text(self):
        return Div(
            HTML(
                'Define the parameters you expect users to specify when requesting this type of experiment.'
            ),
            css_class="text-condensed mb-1"
        )

    def clean(self):
        self.repeated_data = {}
        cleaned_data = super().clean()
        for field in self.repeated_fields:
            cleaned_data['{}_set'.format(field)] = self.data.getlist(field)
            self.fields[field].initial = cleaned_data['{}_set'.format(field)]
        if not self.is_valid():
            for k, v in cleaned_data.items():
                if isinstance(v, list):
                    self.repeated_data[k] = [str(e) for e in v]
        return cleaned_data

    def clean_spec(self):
        data = self.clean()
        spec = {}
        for i, param in enumerate(data['parameter_set']):
            spec[param] = {
                "label": data['label_set'][i],
                "type": data['kind_set'][i],
                "required": data['required_set'][i] == 'True',
            }
            if data['choices_set'][i]:
                spec[param]["choices"] = [(c.strip(), c.strip()) for c in data['choices_set'][i].split(',')]
        validate = fastjsonschema.compile(REQUEST_SPEC_SCHEMA)
        try:
            validate(spec)
        except:
            raise forms.ValidationError('Something is wrong with the defined parameters')
        return spec


WIDTH_CHOICES = (
    (12, 'Full'),
    (6, 'Half'),
    (4, 'Third'),
    (3, 'Quarter'),
    (2, 'Sixth'),
    (0, 'Hidden')
)


class RequestTypeLayoutForm(forms.ModelForm):

    class Meta:
        model = RequestType
        fields = ('layout',)
        widgets = {
            'layout': forms.HiddenInput
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk

        field_styles = self.instance.field_styles()
        parameter_list = Div(css_class="col-12 repeat-group repeat-container")
        for f, style in field_styles.items():
            self.fields[f] = forms.CharField(initial=f)
            self.fields[f].widget.attrs['readonly'] = True
            self.fields["{}_width".format(f)] = forms.CharField(initial=style, label=_('Display Width'))
            self.fields["{}_width".format(f)].widget = forms.Select(choices=WIDTH_CHOICES)
            parameter_list.append(
                Div(
                    Div(Field(f), css_class="col-5"),
                    Div(Field("{}_width".format(f), css_class="select"), css_class="col-5"),
                    Div(
                        Div(
                            HTML('<label>&nbsp;</label>'),
                            HTML(
                                '<a title="Drag to change priority" class="move btn btn-white"><i class="ti ti-move"></i></a>'
                            ),
                            css_class="form-group"
                        ),
                        css_class="col-1"
                    ),
                    css_class="repeat-row row"
                )
            )

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)

        self.body.title = u"Edit Request Type Layout"
        self.body.form_action = reverse_lazy('requesttype-layout', kwargs={'pk': pk})

        self.body.layout = Layout(
            self.help_text(),
            'layout',
            Div(
                Div(
                    parameter_list,
                    css_class="row repeat-wrapper"
                ),
                css_class="repeat"
            )
        )

        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )

    def help_text(self):
        return Div(
            HTML(
                'Re-order the fields and specify how much space each one should be given.'
            ),
            css_class="text-condensed mb-1"
        )

    def clean_layout(self):
        ordered_fields = [f for f in self.data.keys() if f in self.instance.spec.keys()]
        layout = []
        row = []
        for f in ordered_fields:
            width = int(self.data.get("{}_width".format(f)))
            if (sum([r[1] for r in row]) + width) > 12:
                layout.append(row)
                row = []
            row.append([f, width])
        layout.append(row)
        return layout


class RequestForm(forms.ModelForm):
    template = forms.ModelChoiceField(label=_("Copy settings from past request"), queryset=Request.objects.all(),
                                      required=False)
    request = forms.ModelChoiceField(label=_("Use existing request"), queryset=Request.objects.all(),
                                     required=False)

    class Meta:
        model = Request
        fields = ('project', 'name', 'comments', 'kind', 'groups', 'samples', 'template', 'request')
        widgets = {'project': disabled_widget,
                   'comments': forms.Textarea(attrs={'rows': "2"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk
        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)

        if pk:
            self.body.title = u"Edit Request"
            self.body.form_action = reverse_lazy('request-edit', kwargs={'pk': self.instance.pk})
            shipment = self.instance.shipment()
            self.fields['groups'].queryset = self.instance.project.sample_groups.filter(shipment=shipment)
            self.fields['samples'].queryset = self.instance.project.samples.filter(container__shipment=shipment)
            autofill = Div()
        else:
            self.body.title = u"Create a Request"
            self.body.form_action = reverse_lazy('request-new')
            group_pk = self.initial['groups'] and self.initial['groups'][0] or self.initial[
                'samples'] and self.initial['samples'][0].group.pk or None
            shipment = Group.objects.filter(pk=group_pk).first() and Group.objects.filter(pk=group_pk).first().shipment
            requests = self.initial['project'].requests.exclude(groups__pk=group_pk).filter(
                Q(groups__shipment=shipment) | Q(samples__group__shipment=shipment))
            old_requests = Request.objects.filter(project=self.initial['project'])
            self.fields['groups'].widget = forms.MultipleHiddenInput()
            self.fields['samples'].widget = forms.MultipleHiddenInput()

            is_requests = shipment and requests.exists()
            is_template = old_requests.exists()
            if is_template:
                self.fields['template'].queryset = old_requests
            else:
                self.fields['template'].widget = forms.HiddenInput()
            if is_requests:
                self.fields['request'].queryset = requests
            else:
                self.fields['request'].widget = forms.HiddenInput()

            autofill = Div(
                is_requests and Div(
                    Field('request', css_id='request-existing', data_post_action=reverse_lazy('fetch-request'),
                          css_class='select'),
                    css_class="{}".format(is_template and "col-5" or "col-12")) or Div(),
                is_requests and is_template and Div(HTML("""OR"""), css_class='col-2 text-center') or Div(),
                is_template and Div(
                    Field('template', css_id='request-template', data_post_action=reverse_lazy('fetch-request'),
                          css_class='select'),
                    css_class="{}".format(is_requests and "col-5" or "col-12")) or Div(),
                css_class='row'
            )

        related = pk and Div(
            Div(Field('groups', css_class='select'), css_class='col-6'),
            Div(Field('samples', css_class='select'), css_class='col-6'),
            css_class='row'
        ) or Div('groups', 'samples')

        self.body.layout = Layout(
            'project',
            autofill,
            Field('name', css_id='name'),
            Field('kind', css_id='kind'),
            Field('comments', css_id='comments'),
            related
        )
        self.footer.layout = Layout(
            StrictButton("Continue", type="submit", value="Continue", css_class='btn btn-primary'),
        )


class RequestParameterForm(forms.ModelForm):
    template = forms.ModelChoiceField(queryset=Request.objects.all(), required=False)
    request = forms.ModelChoiceField(queryset=Request.objects.all(), required=False)

    class Meta:
        model = Request
        fields = ('kind', 'parameters')
        widgets = {'kind': disabled_widget,
                   'template': disabled_widget,
                   'request': disabled_widget,
                   'parameters': forms.HiddenInput}

    def __init__(self, *args, **kwargs):
        kind_pk = kwargs.pop('kind', None)
        super().__init__(*args, **kwargs)
        pk = self.instance.pk
        if pk:
            kind = self.instance.kind
        else:
            kind_pk = self.initial.get('kind', kind_pk)
            kind = RequestType.objects.filter(pk=kind_pk).first()
        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)

        parameters = Div()
        request = self.initial.get('request') and Request.objects.filter(pk=self.initial.get('request')).first() or None
        template = self.initial.get('template') and Request.objects.filter(pk=self.initial.get('template')).first() or None

        # set the sample, some templates will need it
        self.sample = None if not self.initial.get('samples') else self.initial.get('samples')[0]

        if request:
            self.fields['name'].widget.attrs['readonly'] = True
            self.fields['comments'].widget.attrs['readonly'] = True
        if pk:
            self.body.form_action = reverse_lazy('request-edit', kwargs={'pk': self.instance.pk})
            self.footer.layout = Layout(
                StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
                StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
            )
        else:
            self.body.form_action = reverse_lazy('request-new')
            self.footer.layout = Layout(
                StrictButton('Finish', type='submit', name="submit", value='Finish', css_class='btn btn-primary'),
            )

        if kind:
            self.body.title = u"Request Details".format(kind.name)
            self.fields['kind'].widget = disabled_widget
            self.layout_template = kind.edit_template
            for row in kind.layout:
                param_row = Div(css_class='form-row')
                for param, style in row:
                    info = kind.spec.get(param, {})
                    field_type = 'type' in info and info.pop('type') or 'string'
                    choices = info.get('choices')
                    if info.get('choices'):
                        info['choices'] = tuple(tuple(c) for c in choices)
                    info = {k: v for k, v in info.items() if k not in ['type', 'choices']}
                    if pk:
                        info['initial'] = self.instance.parameters.get(param)
                    elif request:
                        info['initial'] = request.parameters.get(param)
                    elif template:
                        info['initial'] = template.parameters.get(param)
                    if field_type in ['string']:
                        self.fields[param] = forms.CharField(**info)
                    elif field_type == 'json':
                        self.fields[param] = forms.CharField(**info)
                        style = 'hidden'
                    elif field_type == 'number':
                        self.fields[param] = forms.FloatField(**info)
                    elif field_type == 'boolean':
                        self.fields[param] = forms.BooleanField(**info)
                    if choices:
                        self.fields[param].widget=forms.Select(choices=choices)
                    if request:
                        self.fields[param].widget.attrs['readonly'] = True
                    if style == 'hidden':
                        if choices:
                            self.fields[param].widget = forms.MultipleHiddenInput()
                        elif field_type == 'json':
                            self.fields[param].widget = HiddenArea(attrs={'class': 'd-none'})
                        else:
                            self.fields[param].widget = forms.HiddenInput()
                        param_row.append(param)
                    else:
                        param_row.append(Div(param, css_class='col-{}'.format(style)))
                parameters.append(param_row)

        self.body.layout = Layout(
            'kind', 'parameters', parameters,
        )
        if self.instance.pk:
            if self.instance.kind.scope not in [RequestType.SCOPES.ONE_SAMPLE, RequestType.SCOPES.ONE_GROUP]:
                row = Div(css_class='row')
                if self.instance.kind.scope in [RequestType.SCOPES.UNLIMITED, RequestType.SCOPES.GROUPS]:
                    row.append(Div(Field('groups', css_class='select'), css_class='col'))
                if self.instance.kind.scope in [RequestType.SCOPES.UNLIMITED, RequestType.SCOPES.SAMPLES]:
                    row.append(Div(Field('samples', css_class='select'), css_class='col'))
                self.body.layout.append(row)

    def clean_parameters(self):
        cleaned_data = self.cleaned_data
        parameters = {}
        prefix = "{}-".format("".join([self.data.get(k) for k in self.data.keys() if k.endswith('current_step')]))
        for param in cleaned_data['kind'].spec.keys():
            parameters[param] = self.data.get("{}{}".format(prefix, param))
        return parameters


class RequestAdminForm(forms.ModelForm):

    class Meta:
        model = Request
        fields = ('staff_comments','status')
        widgets = {
            'staff_comments': forms.Textarea(attrs={'rows': "4"}),
            'status': forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Update Request"
        self.body.form_action = reverse_lazy('request-admin-edit', kwargs={'pk': pk})
        if self.instance.status != self.instance.STATUS_CHOICES.COMPLETE:
            mark_btn = StrictButton("Mark Complete", type='submit', name="submit", value='done', css_class='btn btn-success')
        else:
            mark_btn = StrictButton("Mark Incomplete", type='submit', name="submit", value='done', css_class='btn btn-warning')

        self.body.layout = Layout(
            Div(
                Div('staff_comments', css_class='col-12'),
                css_class="form-row"
            )
        )
        self.footer.layout = Layout(
            Field('status'),
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary mr-auto"),
            mark_btn,
            StrictButton('Save Comments', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )

    def clean(self):
        status = self.instance.status
        if self.data.get('submit') == 'done':
            if status != self.instance.STATUS_CHOICES.COMPLETE:
                status = self.instance.STATUS_CHOICES.COMPLETE
            else:
                status = self.instance.STATUS_CHOICES.PENDING
        cleaned_data = super().clean()
        cleaned_data['status'] = status
        return cleaned_data


class ShipmentForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(ShipmentForm, self).__init__(*args, **kwargs)
        pk = self.instance.pk

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)

        if pk:
            self.body.title = u"Edit Shipment"
            self.body.form_action = reverse_lazy('shipment-edit', kwargs={'pk': pk})
        else:
            self.body.title = u"Create New Shipment"
            self.body.form_action = reverse_lazy('shipment-new')
        self.body.layout = Layout('project', 'name', 'comments')
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )

    def clean(self):
        cleaned_data = super(ShipmentForm, self).clean()
        if cleaned_data['project'].shipments.filter(name__iexact=cleaned_data.get('name', '')) \
                .exclude(pk=self.instance.pk).exists():
            self.add_error('name', forms.ValidationError("Shipment with this name already exists"))

    class Meta:
        model = Shipment
        fields = ('project', 'name', 'comments',)
        widgets = {'project': disabled_widget,
                   'comments': forms.Textarea(attrs={'rows': "2"})}


class ShipmentCommentsForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(ShipmentCommentsForm, self).__init__(*args, **kwargs)
        pk = self.instance.pk

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Edit shipment"
        self.body.form_action = reverse_lazy('shipment-comments', kwargs={'pk': pk})
        self.body.layout = Layout('storage_location', 'staff_comments')
        self.footer.layout = Layout(
            StrictButton('Unreceive', type='recall', value='Recall', css_class="btn btn-danger"),
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )

    class Meta:
        model = Shipment
        fields = ('staff_comments', 'storage_location')
        widgets = {'staff_comments': forms.Textarea(attrs={'rows': "2"})}


class AutomounterForm(forms.ModelForm):
    class Meta:
        model = Automounter
        fields = ('staff_comments',)
        widgets = {'staff_comments': forms.Textarea(attrs={'rows': "3"})}

    def __init__(self, *args, **kwargs):
        super(AutomounterForm, self).__init__(*args, **kwargs)

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.form_action = reverse_lazy('automounter-edit', kwargs={'pk': self.instance.pk})
        self.body.title = u"Staff Comments for {} Automounter".format(self.instance.beamline.acronym)
        self.body.layout = Layout('staff_comments')
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )


class SampleForm(forms.ModelForm):

    class Meta:
        model = Sample
        fields = ('name', 'barcode', 'comments', 'image')
        widgets = {
            'comments': forms.Textarea(attrs={'rows': "4"}),
        }

    def __init__(self, *args, **kwargs):
        super(SampleForm, self).__init__(*args, **kwargs)
        pk = self.instance.pk

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        if pk:
            self.body.title = u"Edit Sample"
            self.body.form_action = reverse_lazy('sample-edit', kwargs={'pk': pk})
        else:
            self.body.title = u"Create New Sample"
            self.body.form_action = reverse_lazy('sample-new')

        self.body.layout = Layout(
            Div(
                Div('name', css_class='col-6'),
                Div('barcode', css_class='col-6'),
                Div('comments', css_class='col-12'),
                Div('image', css_class='col-12'),
                css_class="form-row"
            )
        )
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )

    def clean(self):
        if 'name' in self.cleaned_data:
            if self.instance.group.samples.exclude(pk=self.instance.pk).filter(name=self.cleaned_data['name']).exists():
                self._errors['name'] = self.error_class(['Each sample in the group must have a unique name'])
            if not re.compile('^[a-zA-Z0-9-_]+[\w]+$').match(self.cleaned_data['name']):
                self._errors['name'] = self.error_class(['Name cannot contain any spaces or special characters'])
        return self.cleaned_data


class SampleAdminForm(forms.ModelForm):

    class Meta:
        model = Sample
        fields = ('staff_comments','collect_status')
        widgets = {
            'staff_comments': forms.Textarea(attrs={'rows': "4"}),
            'collect_status': forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super(SampleAdminForm, self).__init__(*args, **kwargs)
        pk = self.instance.pk

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Update Sample"
        self.body.form_action = reverse_lazy('sample-admin-edit', kwargs={'pk': pk})
        if not self.instance.collect_status:
            mark_btn = StrictButton("Mark Complete", type='submit', name="submit", value='done', css_class='btn btn-success')
        else:
            mark_btn = StrictButton("Mark Incomplete", type='submit', name="submit", value='done', css_class='btn btn-warning')

        self.body.layout = Layout(
            Div(
                Div('staff_comments', css_class='col-12'),
                css_class="form-row"
            )
        )
        self.footer.layout = Layout(
            Field('collect_status'),
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary mr-auto"),
            mark_btn,
            StrictButton('Save Comments', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )

    def clean(self):
        collect_status = self.instance.collect_status
        if self.data.get('submit') == 'done':
            collect_status = not collect_status
        cleaned_data = super().clean()
        cleaned_data['collect_status'] = collect_status
        return cleaned_data


class ShipmentSendForm(forms.ModelForm):
    components = forms.ModelMultipleChoiceField(label='Items included in shipment',
                                                queryset=ComponentType.objects.all(),
                                                required=False)

    class Meta:
        model = Shipment
        fields = ('carrier', 'tracking_code', 'comments')
        widgets = {
            'comments': forms.Textarea(attrs={'rows': "4"}),
        }

    def __init__(self, *args, **kwargs):
        super(ShipmentSendForm, self).__init__(*args, **kwargs)
        errors = Div()
        if self.instance.shipping_errors():
            errors = Div(
                Div(
                    HTML('/ '.join(self.instance.shipping_errors())),
                    css_class="card-header"
                ),
                css_class="card bg-warning"
            )
        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Send Shipment"
        self.body.form_action = reverse_lazy('shipment-send', kwargs={'pk': self.instance.pk})
        self.body.layout = Layout(
            errors,
            Div(
                Div(Field('carrier', css_class="select"), css_class="col-6"),
                Div('tracking_code', css_class="col-6"),
                Div(Field('components', css_class="select"), css_class="col-12"),
                Div('comments', css_class="col-12"),
                css_class="form-row"
            )
        )
        self.footer.layout = Layout(
            StrictButton('Send', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )


class ShipmentReturnForm(forms.ModelForm):
    loaded = forms.BooleanField(label="I have removed these containers from the automounter(s)")

    class Meta:
        model = Shipment
        fields = ['carrier', 'return_code', 'staff_comments']

    def __init__(self, *args, **kwargs):
        super(ShipmentReturnForm, self).__init__(*args, **kwargs)
        if self.instance.containers.filter(parent__isnull=False):
            self.fields['loaded'].label += ": {}".format(
                ','.join(self.instance.containers.filter(parent__isnull=False).values_list('name', flat=True)))
        else:
            self.fields['loaded'].initial = True
            self.fields['loaded'].widget = forms.HiddenInput()
        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Return Shipment"
        self.body.form_action = reverse_lazy('shipment-return', kwargs={'pk': self.instance.pk})
        self.body.layout = Layout(
            Div(
                Div(Field('loaded'), css_class="col-12"),
                css_class="form-row"
            ),
            Div(
                Div(Field('carrier', css_class="select"), css_class="col-6"),
                Div('return_code', css_class="col-6"),
                Div('staff_comments', css_class="col-12"),
                css_class="form-row"
            ),
        )
        self.footer.layout = Layout(
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )


class ShipmentRecallSendForm(forms.ModelForm):
    components = forms.ModelMultipleChoiceField(label='Items included in shipment',
                                                queryset=ComponentType.objects.all(),
                                                required=False)

    class Meta:
        model = Shipment
        fields = ['carrier', 'tracking_code', 'comments']

    def __init__(self, *args, **kwargs):
        super(ShipmentRecallSendForm, self).__init__(*args, **kwargs)
        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Update Shipping Information"
        self.body.form_action = reverse_lazy('shipment-update-send', kwargs={'pk': self.instance.pk})
        self.body.layout = Layout(
            Div(
                Div(Field('carrier', css_class="select"), css_class="col-6"),
                Div('tracking_code', css_class="col-6"),
                Div(Field('components', css_class="select"), css_class="col-12"),
                Div('comments', css_class="col-12"),
                css_class="form-row"
            )
        )
        self.footer.layout = Layout(
            StrictButton('Unsend', type='recall', value='Recall', css_class="btn btn-danger"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )


class ShipmentRecallReturnForm(forms.ModelForm):
    class Meta:
        model = Shipment
        fields = ['carrier', 'return_code', 'staff_comments']

    def __init__(self, *args, **kwargs):
        super(ShipmentRecallReturnForm, self).__init__(*args, **kwargs)
        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Update Shipping Information"
        self.body.form_action = reverse_lazy('shipment-update-return', kwargs={'pk': self.instance.pk})
        self.body.layout = Layout(
            Div(
                Div(Field('carrier', css_class="select"), css_class="col-6"),
                Div('return_code', css_class="col-6"),
                Div('staff_comments', css_class="col-12"),
                css_class="form-row"
            )
        )
        self.footer.layout = Layout(
            StrictButton('Unsend', type='recall', value='Recall', css_class="btn btn-danger"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )


class ShipmentReceiveForm(forms.ModelForm):
    class Meta:
        model = Shipment
        fields = ['storage_location', 'staff_comments']

    def __init__(self, *args, **kwargs):
        super(ShipmentReceiveForm, self).__init__(*args, **kwargs)
        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Receive Shipment?"
        self.body.form_action = reverse_lazy('shipment-receive', kwargs={'pk': self.instance.pk})
        self.body.layout = Layout('storage_location', 'staff_comments')
        self.footer.layout = Layout(
            StrictButton('Receive', type='submit', name="submit", value='submit', css_class='btn btn-primary'),
        )


class ShipmentArchiveForm(forms.ModelForm):
    class Meta:
        model = Shipment
        fields = []

    def __init__(self, *args, **kwargs):
        super(ShipmentArchiveForm, self).__init__(*args, **kwargs)
        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Archive Shipment?"
        self.body.form_action = reverse_lazy('shipment-archive', kwargs={'pk': self.instance.pk})
        self.body.layout = Layout(
            HTML("""{{ object }}"""),
        )
        self.footer.layout = Layout(
            StrictButton('Archive', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )


class ContainerForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(ContainerForm, self).__init__(*args, **kwargs)
        pk = self.instance.pk

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        if pk:
            self.body.title = u"Edit Container"
            self.body.form_action = reverse_lazy("container-edit", kwargs={'pk': pk})
        else:
            self.body.title = u"Create New Container"
            self.body.form_action = reverse_lazy("container-new")
        self.body.layout = Layout('project', 'name', 'shipment', 'comments')
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='submit', css_class='btn btn-primary'),
        )

    def clean_kind(self):
        """ Ensures that the 'kind' of Container cannot be changed when Crystals are associated with it """
        cleaned_data = self.cleaned_data
        if self.instance.pk:
            if self.instance.kind != cleaned_data['kind']:
                if self.instance.num_samples() > 0:
                    raise forms.ValidationError('Cannot change kind of Container when Samples are associated')
        return cleaned_data['kind']

    class Meta:
        model = Container
        fields = ['project', 'name', 'shipment', 'comments']
        widgets = {'project': disabled_widget}


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ('project', 'name', 'comments')
        widgets = {
            'project': disabled_widget,
            'comments': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super(GroupForm, self).__init__(*args, **kwargs)
        pk = self.instance.pk

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        if pk:
            self.body.title = u"Edit Group"
            self.body.form_action = reverse_lazy("group-edit", kwargs={'pk': pk})
        else:
            self.body.title = u"Create New Group"
            self.body.form_action = reverse_lazy("group-new")
        self.body.layout = Layout(
            'project',
            Div(
                Div('name', css_class="col-12"),
                css_class="form-row"
            ),
            Div(
                Div('comments', css_class="col-12"),
                css_class="form-row"
            )
        )
        self.footer.layout = Layout(
            StrictButton('Save', type='submit', name="submit", value='submit', css_class='btn btn-primary'),
        )

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if self.instance.shipment.groups.filter(name=name).exclude(pk=self.instance.pk).exists():
            self.add_error('name', forms.ValidationError("Groups in a shipment must each have a unique name"))
        return name


class ContainerLoadForm(forms.ModelForm):
    class Meta:
        model = Container
        fields = ['parent', 'location']

    def __init__(self, *args, **kwargs):
        form_action = kwargs.pop('form-action')
        super(ContainerLoadForm, self).__init__(*args, **kwargs)
        self.fields['parent'].queryset = self.fields['parent'].queryset.filter(
            kind__locations__accepts=self.instance.kind
        ).distinct()
        if self.instance.parent:
            self.fields['location'].queryset = self.instance.parent.kind.locations.order_by('name')

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Move Container {}".format(self.instance)
        self.body.form_action = form_action
        self.body.layout = Layout(
            Div(
                Div(
                    Field('parent', css_class="select"),
                    css_class="col-6"
                ),
                Div(
                    Field(
                        'location', css_class="select", data_update_on='parent',
                        data_update_url=reverse_lazy("update-locations", kwargs={'pk': 0})
                    ),
                    css_class="col-6"
                ),
                css_class="form-row"
            )
        )
        self.footer.layout = Layout(
            StrictButton('Unload', type="submit", name="unload", value='Unload', css_class='btn btn-danger'),
            StrictButton('Save', type='submit', name="submit", value='submit', css_class='btn btn-primary'),
        )

    def clean(self):
        if self.data.get('submit') == 'Unload':
            self.cleaned_data.update({'location': None})
        else:
            if self.cleaned_data['location']:
                loc_filled = self.cleaned_data['parent'].children.exclude(pk=self.instance.pk).filter(
                    location=self.cleaned_data['location']).exists()
                if loc_filled:
                    self.add_error(None, forms.ValidationError("Container is already loaded in that location"))

        return self.cleaned_data


class EmptyContainers(forms.ModelForm):
    parent = forms.ModelChoiceField(queryset=Container.objects.all(), widget=forms.HiddenInput)

    class Meta:
        model = Project
        fields = []

    def __init__(self, *args, **kwargs):
        form_action = kwargs.pop('form-action')
        super(EmptyContainers, self).__init__(*args, **kwargs)

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Remove containers"
        self.body.form_action = form_action
        self.body.layout = Layout(
            Div(HTML(
                """Any containers owned by <strong>{}</strong> will be removed from the automounter.""".format(
                    self.instance.username.upper()))),
            'parent',
        )
        self.footer.layout = Layout(
            StrictButton('Unload All', type='submit', name="submit", value='submit', css_class='btn btn-danger'),
        )


class LocationLoadForm(forms.ModelForm):
    child = forms.ModelChoiceField(
        label="Container",
        queryset=Container.objects.filter(status=Container.STATES.ON_SITE))
    location = forms.ModelChoiceField(queryset=ContainerLocation.objects.all())

    class Meta:
        model = Container
        fields = ['child', 'location']

    def __init__(self, *args, **kwargs):
        form_action = kwargs.pop('form-action')
        super(LocationLoadForm, self).__init__(*args, **kwargs)

        self.fields['child'].queryset = self.fields['child'].queryset.filter(parent__isnull=True).filter(
            kind__in=self.initial['location'].accepts.all()
        )

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        self.body.title = u"Load Container in location {}".format(self.initial['location'])
        self.body.form_action = form_action

        self.body.layout = Layout(
            Div(
                Field('location', type="hidden"),
                Div(
                    Field('child', css_class="select"),
                    css_class="col-12"
                ),
                css_class="form-row"
            ))
        self.footer.layout = Layout(
            StrictButton('Load', type='submit', name="submit", value='submit', css_class='btn btn-primary'),
        )


class AddShipmentForm(forms.ModelForm):
    class Meta:
        model = Shipment
        fields = ('name', 'comments', 'project')
        widgets = {
            'comments': forms.Textarea(),
        }

    def __init__(self, *args, **kwargs):
        super(AddShipmentForm, self).__init__(*args, **kwargs)

        if self.initial['project'].is_superuser:
            name_row = Div(
                Div(Field('project', css_class="select"), css_class="col-4"),
                Div('name', css_class="col-8"),
                css_class="form-row"
            )
        else:
            self.fields['project'].widget = forms.HiddenInput()
            name_row = Div(
                Field('project', hidden=True),
                Field('name', css_class="col-12")
            )

        self.body = BodyHelper(self)
        self.body.title = "Create a Shipment"
        self.body.form_action = reverse_lazy("shipment-new")
        self.footer = FooterHelper(self)
        self.body.layout = Layout(
            Div(
                Div(
                    Div(
                        HTML(
                            'A default name has been chosen for your shipment. You can modify it as needed. This name '
                            'will be visible to staff at the beamline.'
                        ),
                        css_class="text-condensed mb-1"
                    ),
                    name_row,
                    Field('comments', rows="2", css_class="col-12"),
                    css_class="col-12"
                ),
                css_class="row"
            )
        )
        self.footer.layout = Layout(
            StrictButton("Continue", type="submit", value="Continue", css_class='btn btn-primary'),
        )

    def clean(self):
        cleaned_data = super(AddShipmentForm, self).clean()
        if cleaned_data['project'].shipments.filter(name__iexact=cleaned_data.get('name', '')).exists():
            self.add_error('name', forms.ValidationError("Shipment with this name already exists"))


class ShipmentContainerForm(forms.ModelForm):
    id = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Container
        fields = ('shipment', 'id', 'name', 'kind')
        widgets = {'shipment': forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super(ShipmentContainerForm, self).__init__(*args, **kwargs)
        self.fields['kind'].initial = ContainerType.objects.filter(active=True).first()
        self.fields['kind'].queryset = self.fields['kind'].queryset.filter(active=True)

        self.repeated_fields = ['name', 'kind', 'id']
        self.repeated_data = {}
        for f in self.repeated_fields:
            self.fields['{}_set'.format(f)] = forms.CharField(required=False)

        self.body = BodyHelper(self)
        self.body.title = "Create a Shipment"
        self.body.form_action = reverse_lazy("shipment-new")
        self.footer = FooterHelper(self)
        self.footer.layout = Layout()

        if self.initial.get('shipment'):
            self.repeated_data['name_set'] = [str(c.name) for c in self.initial['shipment'].containers.all()]
            self.repeated_data['id_set'] = [c.pk for c in self.initial['shipment'].containers.all()]
            self.repeated_data['kind_set'] = [c.kind.pk for c in self.initial['shipment'].containers.all()]
            self.fields['kind'].widget.attrs['readonly'] = True
            self.body.form_action = reverse_lazy('shipment-add-containers',
                                                 kwargs={'pk': self.initial['shipment'].pk})
            self.body.title = 'Add Containers to Shipment'
            self.footer.layout.append(
                StrictButton('Save', type='submit', name="submit", value='submit', css_class='btn btn-primary'),
            )
        else:
            self.footer.layout.append(
                StrictButton("Continue", type="submit", value="Continue", css_class='btn btn-primary'),
            )

        self.body.layout = Layout(
            self.help_text(),
            Div(
                Div(
                    Div(
                        Div(
                            Div(Field('name'), css_class="col-5"),
                            Div(Field('kind', css_class="select-alt",  data_repeat_enable="true"), css_class="col-5"),
                            Div(
                                Div(
                                    HTML("<label>&nbsp;</label>"),
                                    Div(
                                        StrictButton(
                                            '<i class="ti ti-minus"></i>',
                                            css_class="btn btn-warning float-right safe-remove"
                                        ),
                                    ),
                                    css_class="form-group"
                                ),
                                css_class="col-2"
                            ),
                            Div('shipment', 'id', css_class="col-12 d-none"),
                            css_class="repeat-row template row"
                        ),
                        css_class="col-12 repeat-group repeat-container"
                    ),
                    Div(
                        StrictButton(
                            "<i class='ti ti-plus'></i> Add Container", type="button",
                            css_class='btn btn-sm btn-success add'
                        ),
                        css_class="col-12 mt-2"
                    ),
                    css_class="row repeat-wrapper"
                ),
                css_class='repeat'
            ),
        )

    def help_text(self):
        if self.initial.get('shipment'):
            return Div(
                HTML(
                    '<h5 class="my-0"><strong>Update containers</strong></h5>'
                    'Use labels that are visible on your containers. <span class="text-danger">Removing a container '
                    'will delete all its contents.</strong>'
                ),
                css_class="text-condensed mb-1"
            )
        else:
            return Div(
                HTML(
                    '<h5 class="my-0"><strong>Add the containers you are sending!</strong></h5>'
                    'To avoid confusion, use labels that are externally visible on your containers. It is possible to '
                    'add more containers later.'
                ),
                css_class="text-condensed mb-1"
            )

    def clean(self):
        self.repeated_data = {}
        cleaned_data = super(ShipmentContainerForm, self).clean()
        for field in self.repeated_fields:
            if 'containers-{}'.format(field) in self.data:
                cleaned_data['{}_set'.format(field)] = self.data.getlist('containers-{}'.format(field))
            else:
                cleaned_data['{}_set'.format(field)] = self.data.getlist(field)
            self.fields[field].initial = cleaned_data['{}_set'.format(field)]
        if not self.is_valid():
            for k, v in cleaned_data.items():
                if isinstance(v, list):
                    self.repeated_data[k] = [str(e) for e in v]
        return cleaned_data


class ShipmentGroupForm(forms.ModelForm):
    id = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Group
        fields = [
            'shipment', 'id', 'priority', 'name', 'comments'
        ]
        widgets = {
            'comments': forms.TextInput(),
            'priority': forms.HiddenInput(),
            'shipment': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super(ShipmentGroupForm, self).__init__(*args, **kwargs)
        self.fields['name'].required = False
        self.body = BodyHelper(self)
        self.body.title = "Create a Shipment"
        self.body.form_action = reverse_lazy("shipment-new")
        self.footer = FooterHelper(self)
        self.footer.layout = Layout()
        if self.initial.get('shipment'):
            groups = self.initial['shipment'].groups.order_by('priority')
            self.repeated_data = {
                'name_set': [str(group.name) for group in groups],
                'priority_set': [group.priority or 0 for group in groups],
                'id_set': [group.pk for group in groups],
                'comments_set': [group.comments or '' for group in groups]
            }

            self.footer.layout.append(
                StrictButton('Save', type='submit', name="submit", value='submit', css_class='btn btn-primary'),
            )

            self.body.title = "Add Groups to Shipment"
            self.body.form_action = reverse_lazy('shipment-add-groups', kwargs={'pk': self.initial['shipment'].pk})
        else:
            self.footer.layout.append(
                StrictButton('Fill Containers', title='Auto-create one group per container (filled with samples) ignoring the groups defined above',
                             type='submit', name="submit", value='Fill', css_class='mr-auto btn btn-warning'),
            )
            self.footer.layout.append(
                StrictButton('Finish', type='submit', name="submit", value='Finish', css_class='btn btn-primary'),
            )


        self.body.layout = Layout(
            self.help_text(),
            Div(
                Div(
                    Div(
                        Div(
                            Div('name', css_class="col-8"),
                            Div(
                                Div(
                                    HTML(
                                        '<label></label>'
                                        '<div class="spaced-buttons">'
                                        '<a title="Drag to change group priority" '
                                        '   class="move btn btn-white">'
                                        '   <i class="ti ti-move"></i>'
                                        '</a>'
                                        '<a title="Edit more group details" href="#group-details--{rowcount}" '
                                        '   class="btn btn-info btn-collapse collapsed"'
                                        '   aria-expanded="false" data-toggle="collapse">'
                                        '   <i class="ti ti-angle-double-right"></i>'
                                        '</a>'
                                        '<a title="Delete Group" class="btn safe-remove btn-warning">'
                                        '   <i class="ti ti-minus"></i>'
                                        '</a>'
                                        '</div>'
                                    ),
                                    css_class="form-group float-right"
                                ),
                                css_class="col-4"
                            ),
                            Div(
                                Div(
                                    Div(Field('comments'), css_class="col-12"),
                                    css_class="form-row"
                                ),
                                Field('shipment'),
                                Field('priority'),
                                Field('id'),
                                css_class="col-12 collapse",
                                id="group-details--{rowcount}"
                            ),
                            css_class="repeat-row template row"
                        ),
                        css_class="col-12 repeat-group repeat-container"
                    ),
                    Div(
                        StrictButton(
                            "<i class='ti ti-plus'></i> Add Group", type="button",
                            css_class='btn btn-sm btn-success add'
                        ),
                        css_class="col-12 mt-2"
                    ),
                    css_class="row repeat-wrapper"
                ),
                css_class='repeat'
            ),
        )

    def help_text(self):
        if self.initial.get('shipment'):
            return Div(
                HTML(
                    '<h5 class="my-0"><strong>Update Groups</strong></h5>'
                    'Samples in new groups can be added later using the <i class="ti ti-paint-bucket"></i> tool. '
                    '<span class="text-danger">Removing a group will also remove any samples in the group</span>'
                ),
                css_class="text-condensed mb-1"
            )
        else:
            return Div(
                HTML(
                    '<h5 class="my-0"><strong>Add Groups</strong></h5>'
                    'Specify groups for similar samples. Groups names will be used as the prefix for sample names. '
                    'Use the <i class="ti ti-paint-bucket"></i> tool to add samples after your shipment is created. '
                ),
                css_class="text-condensed mb-1"
            )

    def clean(self):
        self.repeated_data = {}
        cleaned_data = super(ShipmentGroupForm, self).clean()
        for field in self.Meta.fields:
            if 'groups-{}'.format(field) in self.data:
                cleaned_data['{}_set'.format(field)] = self.data.getlist('groups-{}'.format(field))
            else:
                cleaned_data['{}_set'.format(field)] = self.data.getlist(field)
        if len(set(cleaned_data['name_set'])) != len(cleaned_data['name_set']):
            self.add_error(None, forms.ValidationError("Groups in a shipment must each have a unique name"))
        if not self.is_valid():
            for k, v in cleaned_data.items():
                if isinstance(v, list):
                    self.repeated_data[k] = [str(e) for e in v]
        return cleaned_data


class SSHKeyForm(forms.ModelForm):

    class Meta:
        model = SSHKey
        fields = ['name', 'key', 'project']
        widgets = {
            'key': forms.Textarea(attrs={"placeholder": "Begins with 'ssh-rsa' or 'ssh-dsa'"}),
            'project': forms.HiddenInput()
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        if self.instance.pk:
            self.body.title = u"Edit SSH key"
            self.body.form_action = reverse_lazy('sshkey-edit', kwargs={'pk': self.instance.pk})
        else:
            self.body.title = u"New SSH key"
            self.body.form_action = reverse_lazy('new-sshkey', kwargs={'username': self.initial['project'].username})
        self.body.layout = Layout(
            Div(
                'project',
                Div('name', css_class="col-12"),
                css_class="row"
            ),
            Div(
                Div('key', css_class="col-12"),
                css_class="row"
            ),
        )
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )


class GuideForm(forms.ModelForm):

    class Meta:
        model = Guide
        fields = ['title', 'description', 'kind', 'staff_only', 'modal', 'attachment', 'url', 'priority']
        widgets = {
            'description': forms.Textarea(attrs={"cols": 40, "rows": 7}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.body = BodyHelper(self)
        self.footer = FooterHelper(self)
        if self.instance.pk:
            self.body.title = u"Edit Announcement"
            self.body.form_action = reverse_lazy('guide-edit', kwargs={'pk': self.instance.pk})
        else:
            self.body.title = u"New Announcement"
            self.body.form_action = reverse_lazy('new-guide')
        self.body.layout = Layout(
            Div(
                Div('priority', css_class="col-2"),
                Div('title', css_class="col-10"),
                css_class="row"
            ),
            Div(
                Div('description', css_class="col-12"),
                css_class="row"
            ),
            Div(
                Div('kind', css_class="col-6"),
                Div('url', css_class="col-6", title="Resource examples:\n'youtube:<vid>' or \n'flickr:<album>:<photo>'"),
                css_class="row"
            ),
            Div(
                Div(
                    Field('attachment'),
                    css_class="col-12"
                ),
                css_class="row"
            ),
            Div(
                Div(
                    Div(
                        Field('staff_only', css_class="custom-control-input"),
                        css_class="custom-control custom-switch"
                    ),
                    css_class="col-6"
                ),
                Div(
                    Div(
                        Field('modal', css_class="custom-control-input"),
                        css_class="custom-control custom-switch"
                    ),
                    css_class="col-6"
                ),
                css_class="row"
            ),
        )
        self.footer.layout = Layout(
            StrictButton('Revert', type='reset', value='Reset', css_class="btn btn-secondary"),
            StrictButton('Save', type='submit', name="submit", value='save', css_class='btn btn-primary'),
        )
