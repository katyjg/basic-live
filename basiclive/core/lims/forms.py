import json
import re

import fastjsonschema
from crisp_modals.forms import (
    Button,
    FullWidth,
    HalfWidth,
    ModalModelForm,
    QuarterWidth,
    Row,
    FiveSixthWidth,
    SixthWidth,
    ThirdWidth,
    TwoThirdWidth, ThreeQuarterWidth,
)
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.db.models import Q
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

from basiclive.core.lims.conf import settings
from .icons import render_icon
from .models import Guide, ProjectType, SSHKey, RequestType, Request, REQUEST_SPEC_SCHEMA
from .models import (
    User,
    SystemSettings,
    Project,
    ProjectMembership,
    Shipment,
    Automounter,
    Sample,
    ComponentType,
    Container,
    Group,
    ContainerLocation,
    ContainerType,
    Country,
    Region,
)

disabled_widget = forms.HiddenInput(attrs={'readonly': True})


class HiddenArea(forms.HiddenInput):
    template_name = 'django/forms/widgets/textarea.html'


class ProjectForm(ModalModelForm):
    country = forms.ModelChoiceField(
        queryset=Country.objects.all(),
        required=False,
        empty_label=_("---------")
    )
    region = forms.ModelChoiceField(
        queryset=Region.objects.all(),
        required=False,
        empty_label=_("---------")
    )

    class Meta:
        model = Project
        fields = (
            'title', 'contact_person', 'contact_email', 'contact_phone',
            'carrier', 'account_number', 'shipping_notes', 'organisation', 'department', 'address', 'city', 'country',
            'region', 'postal_code', 'kind', 'alias', 'designation'
        )
        widgets = {
            'shipping_notes': forms.Textarea(attrs={'rows': "2"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        pk = self.instance.pk

        country_val = self.data.get('country') if self.data else (self.instance.country_id if self.instance and self.instance.pk else None)
        if hasattr(country_val, 'pk'):
            country_val = country_val.pk
        if country_val:
            try:
                self.fields['region'].queryset = Region.objects.filter(country_id=int(country_val))
            except (ValueError, TypeError):
                self.fields['region'].queryset = Region.objects.none()
        elif self.data and self.data.get('region'):
            self.fields['region'].queryset = Region.objects.all()
        else:
            self.fields['region'].queryset = Region.objects.none()

        if pk:
            self.body.title = _("Edit Project")
            self.body.form_action = reverse_lazy('project-edit', kwargs={'code': self.instance.code})
        else:
            self.body.title = _("Create New Profile")
            self.body.form_action = reverse_lazy('new-project')

        if not self.user.is_superuser:
            for f in ['kind', 'alias', 'designation']:
                self.fields[f].widget.attrs['readonly'] = True
            self.fields['designation'].widget = forms.MultipleHiddenInput()

        self.body.layout = Layout(
            Row(
                FullWidth('title'),
                style="g-2"
            ),
            Row(
                ThirdWidth(Field('kind', css_class='select')),
                ThirdWidth('alias') if self.user.is_superuser else HalfWidth('alias'),
                ThirdWidth(Field('designation', css_class='select')) if self.user.is_superuser else Div('designation'),
                style="g-2"
            ),
            Row(
                FullWidth('contact_person'),
                HalfWidth('contact_email'),
                HalfWidth(
                    Field(
                        'contact_phone', pattern=r"(\+\d{1,3}-)?\d{3}-\d{3}-\d{4}( x\d+)?$",
                        placeholder="[+9-]999-999-9999[ x9999]"
                    )
                ),
                style="g-2"
            ),
            Row(
                HalfWidth(Field('carrier', css_class="select")),
                HalfWidth('account_number'),
                style="g-2"
            ),
            Row(
                FullWidth('shipping_notes'),
            ),
            Row(
                HalfWidth('organisation'),
                HalfWidth('department'),
                style="g-2"
            ),
            Row(
                TwoThirdWidth('address'),
                ThirdWidth('city'),
                style="g-2"
            ),
            Row(
                ThirdWidth(Field('country', css_class='select')),
                ThirdWidth(Field('region', css_class='select')),
                ThirdWidth('postal_code'),
                style="g-2"
            ),
        )
        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='submit', style='btn-primary'),
            HTML("""{% load static %}<script src="{% static 'lims/js/basiclive-countries.js' %}"></script>""")
        )

    def clean(self):
        cleaned_data = super().clean()
        country = cleaned_data.get('country')
        region = cleaned_data.get('region')
        if region:
            if not country:
                cleaned_data['country'] = region.country
            elif region.country_id != country.id:
                self.add_error('region', _("The selected region does not belong to the selected country."))
        return cleaned_data


class NewProjectForm(ModalModelForm):
    pi = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=True,
        label=_("Principal Investigator")
    )
    delegate = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        label=_("Delegate")
    )
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        label=_("Team Members")
    )
    country = forms.ModelChoiceField(
        queryset=Country.objects.all(),
        required=False,
        empty_label=_("---------")
    )
    region = forms.ModelChoiceField(
        queryset=Region.objects.all(),
        required=False,
        empty_label=_("---------")
    )

    class Meta:
        model = Project
        fields = (
            'code', 'title', 'kind', 'alias', 'designation',
            'contact_person', 'contact_email', 'contact_phone',
            'carrier', 'account_number', 'shipping_notes',
            'organisation', 'department', 'address', 'city', 'country',
            'region', 'postal_code'
        )
        widgets = {
            'shipping_notes': forms.Textarea(attrs={'rows': "2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        country_val = self.data.get('country') if self.data else (self.instance.country_id if self.instance and self.instance.pk else None)
        if hasattr(country_val, 'pk'):
            country_val = country_val.pk
        if country_val:
            try:
                self.fields['region'].queryset = Region.objects.filter(country_id=int(country_val))
            except (ValueError, TypeError):
                self.fields['region'].queryset = Region.objects.none()
        elif self.data and self.data.get('region'):
            self.fields['region'].queryset = Region.objects.all()
        else:
            self.fields['region'].queryset = Region.objects.none()

        self.fields['kind'].initial = ProjectType.objects.first()

        self.body.title = _("Create New Project")
        self.body.form_action = reverse_lazy('new-project')
        self.body.layout = Layout(
            Row(
                HalfWidth('code'),
                HalfWidth(Field('kind', css_class="select")),
                style="g-2"
            ),
            Row(
                FullWidth('title'),
                style="g-2"
            ),
            Row(
                HalfWidth(Field('pi', css_class="select")),
                HalfWidth(Field('delegate', css_class="select")),
                style="g-2"
            ),
            Row(
                FullWidth(Field('members', css_class="select")),
                style="g-2"
            ),
            Row(
                HalfWidth('alias'),
                HalfWidth(Field('designation', css_class='select')),
                style="g-2"
            ),
            Row(
                FullWidth('contact_person'),
                HalfWidth('contact_email'),
                HalfWidth(
                    Field(
                        'contact_phone', pattern=r"(\+\d{1,3}-)?\d{3}-\d{3}-\d{4}( x\d+)?$",
                        placeholder="[+9-]999-999-9999[ x9999]"
                    )
                ),
                style="g-2"
            ),
            Row(
                HalfWidth(Field('carrier', css_class="select")),
                HalfWidth('account_number'),
                style="g-2"
            ),
            Row(
                FullWidth('shipping_notes'),
            ),
            Row(
                HalfWidth('organisation'),
                HalfWidth('department'),
                style="g-2"
            ),
            Row(
                TwoThirdWidth('address'),
                ThirdWidth('city'),
                style="g-2"
            ),
            Row(
                ThirdWidth(Field('country', css_class='select')),
                ThirdWidth(Field('region', css_class='select')),
                ThirdWidth('postal_code'),
                style="g-2"
            ),
        )
        self.footer.set_buttons(
            Button('Save', type='submit', name="submit", value='submit', style='btn-primary'),
            HTML("""{% load static %}<script src="{% static 'lims/js/basiclive-countries.js' %}"></script>""")
        )

    def clean(self):
        cleaned_data = super().clean()
        country = cleaned_data.get('country')
        region = cleaned_data.get('region')
        if region:
            if not country:
                cleaned_data['country'] = region.country
            elif region.country_id != country.id:
                self.add_error('region', _("The selected region does not belong to the selected country."))
        return cleaned_data

    def save(self, commit=True):
        project = super().save(commit=False)
        pi = self.cleaned_data['pi']
        project.pi = pi
        if commit:
            project.save()
            self.save_m2m()

            # Create or update PI membership
            ProjectMembership.objects.update_or_create(
                project=project,
                user=pi,
                defaults={'role': ProjectMembership.Role.PI}
            )

            # Create or update Delegate membership if provided
            delegate = self.cleaned_data.get('delegate')
            if delegate:
                ProjectMembership.objects.update_or_create(
                    project=project,
                    user=delegate,
                    defaults={'role': ProjectMembership.Role.DELEGATE}
                )

            # Create or update Team Memberships
            members = self.cleaned_data.get('members') or []
            for member in members:
                if member != pi and member != delegate:
                    ProjectMembership.objects.update_or_create(
                        project=project,
                        user=member,
                        defaults={'role': ProjectMembership.Role.MEMBER}
                    )

        return project


class RequestTypeForm(ModalModelForm):
    parameter = forms.CharField(max_length=32, required=False, label=_("Field*"))
    required = forms.ChoiceField(choices=((False, 'No'), (True, 'Yes')), required=False)
    label = forms.CharField(max_length=64, required=False)
    kind = forms.ChoiceField(required=False)
    choices = forms.CharField(max_length=512, required=False)

    class Meta:
        model = RequestType
        fields = ('name', 'description', 'spec', 'scope', 'edit_template', 'view_template')
        widgets = {
            'description': forms.TextInput(),
            'scope': forms.Select(attrs={'class': 'select'}, choices=RequestType.SCOPES),
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
            self.fields[f'{f}_set'] = forms.CharField(required=False)
        if pk:
            spec = self.instance.spec
            parameters = spec.keys()
            self.repeated_data['parameter_set'] = [param for param in parameters]
            self.repeated_data['kind_set'] = [spec[param]['type'] for param in parameters]
            self.repeated_data['label_set'] = [spec[param]['label'] for param in parameters]
            self.repeated_data['choices_set'] = [
                spec[param].get('choices') and ', '.join(c[0] for c in spec[param]['choices']) or '' for param in
                parameters]
            self.repeated_data['required_set'] = [str(spec[param]['required']) for param in parameters]

        if pk:
            self.body.title = "Edit Request Type"
            self.body.form_action = reverse_lazy('request-type-edit', kwargs={'pk': pk})
        else:
            self.body.title = "Create Request Type"
            self.body.form_action = reverse_lazy('new-requesttype')

        self.body.layout = Layout(
            self.help_text(),
            Row(
                'spec',
                ThirdWidth('name'),
                ThirdWidth('scope'),
                ThirdWidth('edit_template'),
                TwoThirdWidth('description'),
                ThirdWidth('view_template'),
                style="g-2"
            ),
            Div(
                Row(
                    FullWidth(
                        Row(
                            SixthWidth(Field('parameter')),
                            SixthWidth(Field('kind', css_class="select-alt", data_repeat_enable="true")),
                            QuarterWidth(Field('label')),
                            QuarterWidth(Field('choices')),
                            Div(
                                Field('required', css_class="select-alt", data_repeat_enable="true"),
                                css_class="col-1"
                            ),
                            Div(
                                Div(
                                    HTML('<label>&nbsp;</label>'),
                                    Div(
                                        Button(
                                            render_icon('minus'),
                                            style="btn-warning float-end safe-remove"
                                        ),
                                    ),
                                    css_class="mb-3"
                                ),
                                css_class="col-1"
                            ),
                            style="repeat-row template g-2"
                        ),
                        style="repeat-group repeat-container"
                    ),
                    FullWidth(
                        Button(
                            f"{render_icon('plus')} Add Parameter", type="button",
                            style='btn-sm btn-success add'
                        ),
                        style="mt-2"
                    ),
                    style="repeat-wrapper"
                ),
                css_class='repeat'
            ),
        )

        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
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
    (10, 'Five Sixths'),
    (9, 'Three Quarters'),
    (8, 'Two Thirds'),
    (6, 'Half'),
    (4, 'Third'),
    (3, 'Quarter'),
    (2, 'Sixth'),
    (0, 'Hidden'),

)


class RequestTypeLayoutForm(ModalModelForm):
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
        parameter_list = FullWidth(style="repeat-group repeat-container")
        for f, style in field_styles.items():
            self.fields[f] = forms.CharField(initial=f)
            self.fields[f].widget.attrs['readonly'] = True
            self.fields[f"{f}_width"] = forms.CharField(initial=style, label=_('Display Width'))
            self.fields[f"{f}_width"].widget = forms.Select(choices=WIDTH_CHOICES)
            parameter_list.append(
                Row(
                    Div(Field(f), css_class="col-5"),
                    Div(Field(f"{f}_width", css_class="select"), css_class="col-5"),
                    Div(
                        Div(
                            HTML('<label>&nbsp;</label>'),
                            HTML(
                                f'<a title="Drag to change priority" class="move btn btn-white">{render_icon("move")}</a>'
                            ),
                            css_class="mb-3"
                        ),
                        css_class="col-1"
                    ),
                    style="repeat-row"
                )
            )

        self.body.title = "Edit Request Type Layout"
        self.body.form_action = reverse_lazy('request-type-layout', kwargs={'pk': pk})

        self.body.layout = Layout(
            self.help_text(),
            'layout',
            Div(
                Row(
                    parameter_list,
                    style="repeat-wrapper"
                ),
                css_class="repeat"
            )
        )

        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
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
            width = int(self.data.get(f"{f}_width"))
            if (sum([r[1] for r in row]) + width) > 12:
                layout.append(row)
                row = []
            row.append([f, width])
        layout.append(row)
        return layout


class RequestForm(ModalModelForm):
    template = forms.ModelChoiceField(
        label=_("Copy Settings From"), queryset=Request.objects.all(),
        required=False
    )

    class Meta:
        model = Request
        fields = ('project', 'name', 'comments', 'kind', 'groups', 'samples', 'template')
        widgets = {
            'project': disabled_widget,
            'groups': forms.MultipleHiddenInput,
            'samples': forms.MultipleHiddenInput,
            'comments': forms.Textarea(attrs={'rows': "2"})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk
        if pk is not None:
            self.body.title = "Edit Request"
            self.body.form_action = reverse_lazy('request-edit', kwargs={'pk': self.instance.pk})
        else:
            self.body.title = "Create Request"
            self.body.form_action = reverse_lazy('request-new')

        group = sample = None
        if self.initial['groups']:
            group = self.initial['groups'][0]
        if self.initial['samples']:
            sample = self.initial['samples'][0]
        self.sample = sample
        if self.sample and not group:
            group = self.sample.group

        shipment = None if not group else group.shipment
        requests = Request.objects.filter(
            project=self.initial['project']
        ).exclude(groups=group).filter(
            Q(groups__shipment=shipment) | Q(samples__group__shipment=shipment)
        )
        old_requests = Request.objects.filter(project=self.initial['project'])

        is_requests = shipment and requests.exists()
        is_template = old_requests.exists()
        if is_template:
            self.fields['template'].queryset = old_requests
        else:
            self.fields['template'].widget = forms.HiddenInput()

        autofill = Row(
            Div(
                Field(
                    'template', css_id='request-template', data_post_action=reverse_lazy('fetch-request'),
                    css_class='select'
                ),
                css_class='col-12'
            ) if is_template else Div(),
        )

        if pk:
            related = Row(
                HalfWidth(Field('groups', css_class='select')),
                HalfWidth(Field('samples', css_class='select')),
            )
        else:
            related = Div('groups', 'samples')

        self.body.layout = Layout(
            'project',
            autofill,
            Field('kind', css_id='kind'),
            Field('name', css_id='name'),
            Field('comments', css_id='comments'),
            related
        )
        self.footer.set_buttons(
            Button("Continue", type="submit", value="Continue", style='btn-primary'),
        )


class RequestParameterForm(ModalModelForm):
    template = forms.ModelChoiceField(queryset=Request.objects.all(), required=False)
    request = forms.ModelChoiceField(queryset=Request.objects.all(), required=False)

    class Meta:
        model = Request
        fields = ('kind', 'name', 'comments', 'samples', 'groups', 'parameters')
        widgets = {
            'kind': disabled_widget,
            'name': disabled_widget,
            'samples': forms.MultipleHiddenInput,
            'groups': forms.MultipleHiddenInput,
            'comments': disabled_widget,
            'template': disabled_widget,
            'request': disabled_widget,
            'parameters': forms.HiddenInput
        }

    def __init__(self, *args, **kwargs):
        kind_pk = kwargs.pop('kind', None)
        super().__init__(*args, **kwargs)
        pk = self.instance.pk
        if pk:
            kind = self.instance.kind
        else:
            kind_pk = self.initial.get('kind', kind_pk)
            kind = RequestType.objects.filter(pk=kind_pk).first()

        parameters = Div()
        request = self.initial.get('request') and Request.objects.filter(pk=self.initial.get('request')).first() or None
        template = self.initial.get('template') and Request.objects.filter(
            pk=self.initial.get('template')
        ).first() or None

        # set the sample, some templates will need it
        self.sample = None if not self.initial.get('samples') else self.initial.get('samples')[0]

        if request:
            self.fields['name'].widget.attrs['readonly'] = True
            self.fields['comments'].widget.attrs['readonly'] = True
        if pk:
            self.body.form_action = reverse_lazy('request-edit', kwargs={'pk': self.instance.pk})
            self.footer.set_buttons(
                Button('Revert', type='reset', value='Reset', style="btn-secondary"),
                Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
            )
        else:
            self.body.form_action = reverse_lazy('request-new')
            self.footer.set_buttons(
                Button('Finish', type='submit', name="submit", value='Finish', style='btn-primary'),
            )

        if kind:
            self.body.title = "Request Details".format(kind.name)
            self.fields['kind'].widget = disabled_widget
            self.layout_template = kind.edit_template
            for row in kind.layout:
                param_row = Row(style='g-2')
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
                        self.fields[param].widget = forms.Select(choices=choices)
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
            'kind', 'name', 'parameters', parameters,
        )
        if self.instance.pk:
            if self.instance.kind.scope not in [RequestType.SCOPES.ONE_SAMPLE, RequestType.SCOPES.ONE_GROUP]:
                row = Row()
                if self.instance.kind.scope in [RequestType.SCOPES.UNLIMITED, RequestType.SCOPES.GROUPS]:
                    row.append(Div(Field('groups', css_class='select'), css_class='col'))
                if self.instance.kind.scope in [RequestType.SCOPES.UNLIMITED, RequestType.SCOPES.SAMPLES]:
                    row.append(Div(Field('samples', css_class='select'), css_class='col'))
                self.body.layout.append(row)

    def clean_parameters(self):
        cleaned_data = self.cleaned_data
        parameters = {}
        prefix = f"{''.join([self.data.get(k) for k in self.data.keys() if k.endswith('current_step')])}-"
        for param, param_type in cleaned_data['kind'].spec.items():
            if param_type['type'] == 'json':
                parameters[param] = json.loads(self.data.get(f"{prefix}{param}"))
            elif param_type['type'] == 'number':
                parameters[param] = float(self.data.get(f"{prefix}{param}"))
            elif param_type['type'] == 'boolean':
                parameters[param] = self.data.get(f"{prefix}{param}") in ['True', 'true', '1', 1, 'on', 'yes', 'Yes', 'On']
            else:
                parameters[param] = self.data.get(f"{prefix}{param}")
        return parameters


class RequestAdminForm(ModalModelForm):
    class Meta:
        model = Request
        fields = ('staff_comments', 'status')
        widgets = {
            'staff_comments': forms.Textarea(attrs={'rows': "4"}),
            'status': forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk

        self.body.title = "Update Request"
        self.body.form_action = reverse_lazy('request-admin-edit', kwargs={'pk': pk})
        if self.instance.status != self.instance.STATUS_CHOICES.COMPLETE:
            mark_btn = Button(
                "Mark Complete", type='submit', name="submit", value='done', style='btn-success'
            )
        else:
            mark_btn = Button(
                "Mark Incomplete", type='submit', name="submit", value='done', style='btn-warning'
            )

        self.body.layout = Layout(
            Row(
                FullWidth('staff_comments'),
                style="g-2"
            )
        )
        self.footer.set_buttons(
            Field('status'),
            Button('Revert', type='reset', value='Reset', style="btn-secondary me-auto"),
            mark_btn,
            Button('Save Comments', type='submit', name="submit", value='save', style='btn-primary'),
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


class ShipmentForm(ModalModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk

        if pk:
            self.body.title = "Edit Shipment"
            self.body.form_action = reverse_lazy('shipment-edit', kwargs={'pk': pk})
        else:
            self.body.title = "Create New Shipment"
            self.body.form_action = reverse_lazy('shipment-new')
        self.body.layout = Layout('project', 'name', 'comments')
        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )

    def clean(self):
        cleaned_data = super().clean()
        project = cleaned_data.get('project')
        if project:
            if not self.instance.pk and project.is_expired:
                self.add_error('project', forms.ValidationError("Cannot create a shipment for an expired project"))
            if project.shipments.filter(name__iexact=cleaned_data.get('name', '')) \
                    .exclude(pk=self.instance.pk).exists():
                self.add_error('name', forms.ValidationError("Shipment with this name already exists"))
        return cleaned_data

    class Meta:
        model = Shipment
        fields = ('project', 'name', 'comments',)
        widgets = {
            'project': disabled_widget,
            'comments': forms.Textarea(attrs={'rows': "2"})
        }


class ShipmentCommentsForm(ModalModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk

        self.body.title = "Edit shipment"
        self.body.form_action = reverse_lazy('shipment-comments', kwargs={'pk': pk})
        self.body.layout = Layout('storage_location', 'staff_comments')
        self.footer.set_buttons(
            Button('Unreceive', type='recall', value='Recall', style="btn-danger"),
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )

    class Meta:
        model = Shipment
        fields = ('staff_comments', 'storage_location')
        widgets = {'staff_comments': forms.Textarea(attrs={'rows': "2"})}


class AutomounterForm(ModalModelForm):
    class Meta:
        model = Automounter
        fields = ('staff_comments',)
        widgets = {'staff_comments': forms.Textarea(attrs={'rows': "3"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.body.form_action = reverse_lazy('automounter-edit', kwargs={'pk': self.instance.pk})
        self.body.title = "Staff Comments for {} Automounter".format(self.instance.beamline.acronym)
        self.body.layout = Layout('staff_comments')
        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )


class SampleForm(ModalModelForm):
    class Meta:
        model = Sample
        fields = ('name', 'barcode', 'comments', 'image')
        widgets = {
            'comments': forms.Textarea(attrs={'rows': "4"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk

        if pk:
            self.body.title = "Edit Sample"
            self.body.form_action = reverse_lazy('sample-edit', kwargs={'pk': pk})
        else:
            self.body.title = "Create New Sample"
            self.body.form_action = reverse_lazy('sample-new')

        self.body.layout = Layout(
            Row(
                HalfWidth('name'),
                HalfWidth('barcode'),
                FullWidth('comments'),
                FullWidth('image'),
                style="g-2"
            )
        )
        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )

    def clean(self):
        if 'name' in self.cleaned_data:
            if self.instance.group.samples.exclude(pk=self.instance.pk).filter(name=self.cleaned_data['name']).exists():
                self._errors['name'] = self.error_class(['Each sample in the group must have a unique name'])
            if not re.compile(r'^[a-zA-Z0-9-_]+[\w]+$').match(self.cleaned_data['name']):
                self._errors['name'] = self.error_class(['Name cannot contain any spaces or special characters'])
        return self.cleaned_data


class SampleAdminForm(ModalModelForm):
    class Meta:
        model = Sample
        fields = ('staff_comments', 'collect_status')
        widgets = {
            'staff_comments': forms.Textarea(attrs={'rows': "4"}),
            'collect_status': forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk

        self.body.title = "Update Sample"
        self.body.form_action = reverse_lazy('sample-admin-edit', kwargs={'pk': pk})
        if not self.instance.collect_status:
            mark_btn = Button(
                "Mark Complete", type='submit', name="submit", value='done', style='btn-success'
            )
        else:
            mark_btn = Button(
                "Mark Incomplete", type='submit', name="submit", value='done', style='btn-warning'
            )

        self.body.layout = Layout(
            Row(
                FullWidth('staff_comments'),
                style="g-2"
            )
        )
        self.footer.set_buttons(
            Field('collect_status'),
            Button('Revert', type='reset', value='Reset', style="btn-secondary me-auto"),
            mark_btn,
            Button('Save Comments', type='submit', name="submit", value='save', style='btn-primary'),
        )

    def clean(self):
        collect_status = self.instance.collect_status
        if self.data.get('submit') == 'done':
            collect_status = not collect_status
        cleaned_data = super().clean()
        cleaned_data['collect_status'] = collect_status
        return cleaned_data


class ShipmentSendForm(ModalModelForm):
    components = forms.ModelMultipleChoiceField(
        label='Items included in shipment',
        queryset=ComponentType.objects.all(),
        required=False
    )

    class Meta:
        model = Shipment
        fields = ('carrier', 'tracking_code', 'comments')
        widgets = {
            'comments': forms.Textarea(attrs={'rows': "4"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        errors = Div()
        if self.instance.shipping_errors():
            errors = Div(
                Div(
                    HTML('/ '.join(self.instance.shipping_errors())),
                    css_class="card-header"
                ),
                css_class="card bg-warning"
            )
        self.body.title = "Send Shipment"
        self.body.form_action = reverse_lazy('shipment-send', kwargs={'pk': self.instance.pk})
        self.body.layout = Layout(
            errors,
            Row(
                HalfWidth(Field('carrier', css_class="select")),
                HalfWidth('tracking_code'),
                FullWidth(Field('components', css_class="select")),
                FullWidth('comments'),
                style="g-2"
            )
        )
        self.footer.set_buttons(
            Button('Send', type='submit', name="submit", value='save', style='btn-primary'),
        )


class ShipmentReturnForm(ModalModelForm):
    loaded = forms.BooleanField(label="I have removed these containers from the automounter(s)")

    class Meta:
        model = Shipment
        fields = ['carrier', 'return_code', 'staff_comments']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.containers.filter(parent__isnull=False):
            self.fields['loaded'].label += ": {}".format(
                ','.join(self.instance.containers.filter(parent__isnull=False).values_list('name', flat=True))
            )
        else:
            self.fields['loaded'].initial = True
            self.fields['loaded'].widget = forms.HiddenInput()
        self.body.title = "Return Shipment"
        self.body.form_action = reverse_lazy('shipment-return', kwargs={'pk': self.instance.pk})
        self.body.layout = Layout(
            Row(
                FullWidth(Field('loaded')),
                style="g-2"
            ),
            Row(
                HalfWidth(Field('carrier', css_class="select")),
                HalfWidth('return_code'),
                FullWidth('staff_comments'),
                style="g-2"
            ),
        )
        self.footer.set_buttons(
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )


class ShipmentRecallSendForm(ModalModelForm):
    components = forms.ModelMultipleChoiceField(
        label='Items included in shipment',
        queryset=ComponentType.objects.all(),
        required=False
    )

    class Meta:
        model = Shipment
        fields = ['carrier', 'tracking_code', 'comments']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.body.title = "Recall Shipment"
        self.body.layout = Layout(
            Row(
                HalfWidth(Field('carrier', css_class="select")),
                HalfWidth('tracking_code'),
                FullWidth(Field('components', css_class="select")),
                FullWidth('comments'),
                style="g-2"
            )
        )
        self.footer.set_buttons(
            Button('Recall', type='recall', value='Recall', style="btn-danger"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )


class ShipmentRecallReturnForm(ModalModelForm):
    class Meta:
        model = Shipment
        fields = ['carrier', 'return_code', 'staff_comments']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.body.title = "Recall Shipment"
        self.body.layout = Layout(
            Row(
                HalfWidth(Field('carrier', css_class="select")),
                HalfWidth('return_code'),
                FullWidth('staff_comments'),
                style="g-2"
            )
        )
        self.footer.set_buttons(
            Button('Recall', type='recall', value='Recall', style="btn-danger"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )


class ShipmentReceiveForm(ModalModelForm):
    class Meta:
        model = Shipment
        fields = ['storage_location', 'staff_comments']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.body.title = "Receive Shipment?"
        self.body.layout = Layout('storage_location', 'staff_comments')
        self.footer.set_buttons(
            Button('Receive', type='submit', name="submit", value='submit', style='btn-primary'),
        )


class ShipmentArchiveForm(ModalModelForm):
    class Meta:
        model = Shipment
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.body.title = "Archive Shipment?"
        self.body.form_action = reverse_lazy('shipment-archive', kwargs={'pk': self.instance.pk})
        self.body.layout = Layout(
            HTML("""{{ object }}"""),
        )
        self.footer.set_buttons(
            Button('Archive', type='submit', name="submit", value='save', style='btn-primary'),
        )


class ContainerForm(ModalModelForm):
    class Meta:
        model = Container
        fields = ['project', 'name', 'comments']
        widgets = {
            'project': disabled_widget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk

        if pk:
            self.body.title = "Edit Container"
            self.body.form_action = reverse_lazy("container-edit", kwargs={'pk': pk})
        else:
            self.body.title = "Create New Container"
            self.body.form_action = reverse_lazy("container-new")

        self.body.layout = Layout('project', 'name', 'comments')
        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='submit', style='btn-primary'),
        )

    def clean_kind(self):
        """ Ensures that the 'kind' of Container cannot be changed when Crystals are associated with it """
        cleaned_data = self.cleaned_data
        if self.instance.pk:
            if self.instance.kind != cleaned_data['kind']:
                if self.instance.num_samples() > 0:
                    raise forms.ValidationError('Cannot change kind of Container when Samples are associated')
        return cleaned_data['kind']


class GroupForm(ModalModelForm):
    class Meta:
        model = Group
        fields = ('project', 'name', 'comments')
        widgets = {
            'project': disabled_widget,
            'comments': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pk = self.instance.pk

        if pk:
            self.body.title = "Edit Group"
            self.body.form_action = reverse_lazy("group-edit", kwargs={'pk': pk})
        else:
            self.body.title = "Create New Group"
            self.body.form_action = reverse_lazy("group-new")
        self.body.layout = Layout(
            'project',
            Row(
                FullWidth('name'),
                style="g-2"
            ),
            Row(
                FullWidth('comments'),
                style="g-2"
            )
        )
        self.footer.set_buttons(
            Button('Save', type='submit', name="submit", value='submit', style='btn-primary'),
        )

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if self.instance.shipment.groups.filter(name=name).exclude(pk=self.instance.pk).exists():
            self.add_error('name', forms.ValidationError("Groups in a shipment must each have a unique name"))
        return name


class ContainerLoadForm(ModalModelForm):
    class Meta:
        model = Container
        fields = ['parent', 'location']

    def __init__(self, *args, **kwargs):
        form_action = kwargs.pop('form-action')
        super().__init__(*args, **kwargs)
        self.fields['parent'].queryset = self.fields['parent'].queryset.filter(
            kind__locations__accepts=self.instance.kind
        ).distinct()
        if self.instance.parent:
            self.fields['location'].queryset = self.instance.parent.kind.locations.order_by('name')

        self.body.title = "Move Container {}".format(self.instance)
        self.body.form_action = form_action
        self.body.layout = Layout(
            Row(
                HalfWidth(Field('parent', css_class="select")),
                HalfWidth(
                    Field(
                        'location', css_class="select", data_update_on='parent',
                        data_update_url=reverse_lazy("update-locations", kwargs={'pk': 0})
                    )
                ),
                style="g-2"
            )
        )
        self.footer.set_buttons(
            Button('Unload', type="submit", name="unload", value='Unload', style='btn-danger'),
            Button('Save', type='submit', name="submit", value='submit', style='btn-primary'),
        )

    def clean(self):
        if self.data.get('submit') == 'Unload':
            self.cleaned_data.update({'location': None})
        else:
            if self.cleaned_data['location']:
                loc_filled = self.cleaned_data['parent'].children.exclude(pk=self.instance.pk).filter(
                    location=self.cleaned_data['location']
                ).exists()
                if loc_filled:
                    self.add_error(None, forms.ValidationError("Container is already loaded in that location"))

        return self.cleaned_data


class EmptyContainers(ModalModelForm):
    parent = forms.ModelChoiceField(queryset=Container.objects.all(), widget=forms.HiddenInput)

    class Meta:
        model = Project
        fields = []

    def __init__(self, *args, **kwargs):
        form_action = kwargs.pop('form-action')
        super().__init__(*args, **kwargs)

        self.body.title = "Remove containers"
        self.body.form_action = form_action
        self.body.layout = Layout(
            Div(
                HTML(
                    """Any containers owned by <strong>{}</strong> will be removed from the automounter.""".format(
                        self.instance.name.upper()
                    )
                )
            ),
            'parent',
        )
        self.footer.set_buttons(
            Button('Unload All', type='submit', name="submit", value='submit', style='btn-danger'),
        )


class LocationLoadForm(ModalModelForm):
    child = forms.ModelChoiceField(
        label="Container",
        queryset=Container.objects.filter(status=Container.STATES.ON_SITE)
    )
    location = forms.ModelChoiceField(queryset=ContainerLocation.objects.all())

    class Meta:
        model = Container
        fields = ['child', 'location']

    def __init__(self, *args, **kwargs):
        form_action = kwargs.pop('form-action')
        super().__init__(*args, **kwargs)

        self.fields['child'].queryset = self.fields['child'].queryset.filter(parent__isnull=True).filter(
            kind__in=self.initial['location'].accepts.all()
        )

        self.body.title = "Load Container in location {}".format(self.initial['location'])
        self.body.form_action = form_action

        self.body.layout = Layout(
            Row(
                Field('location', type="hidden"),
                FullWidth(Field('child', css_class="select")),
                style="g-2"
            )
        )
        self.footer.set_buttons(
            Button('Load', type='submit', name="submit", value='submit', style='btn-primary'),
        )


class AddShipmentForm(ModalModelForm):
    class Meta:
        model = Shipment
        fields = ('name', 'comments', 'project')
        widgets = {
            'comments': forms.Textarea(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].queryset = Project.objects.operational()

        if user and user.is_superuser:
            name_row = Row(
                ThirdWidth(Field('project', css_class="select")),
                TwoThirdWidth('name'),
                style="g-2"
            )
        else:
            self.fields['project'].widget = forms.HiddenInput()
            name_row = Div(
                Field('project', hidden=True),
                Field('name', css_class="col-12")
            )

        self.body.title = "Create a Shipment"
        self.body.form_action = reverse_lazy("shipment-new")
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
        self.footer.set_buttons(
            Button("Continue", type="submit", value="Continue", style='btn-primary'),
        )

    def clean(self):
        cleaned_data = super(AddShipmentForm, self).clean()
        project = cleaned_data.get('project')
        if project:
            if project.is_expired:
                self.add_error('project', forms.ValidationError("Cannot create a shipment for an expired project"))
            if project.shipments.filter(name__iexact=cleaned_data.get('name', '')).exists():
                self.add_error('name', forms.ValidationError("Shipment with this name already exists"))
        return cleaned_data


class ShipmentContainerForm(ModalModelForm):
    id = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Container
        fields = ('shipment', 'id', 'name', 'kind')
        widgets = {'shipment': forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kind'].initial = ContainerType.objects.filter(active=True).first()
        self.fields['kind'].queryset = self.fields['kind'].queryset.filter(active=True)

        self.repeated_fields = ['name', 'kind', 'id']
        self.repeated_data = {}
        for f in self.repeated_fields:
            self.fields['{}_set'.format(f)] = forms.CharField(required=False)

        self.body.title = "Create a Shipment"
        self.body.form_action = reverse_lazy("shipment-new")

        if self.initial.get('shipment'):
            self.repeated_data['name_set'] = [str(c.name) for c in self.initial['shipment'].containers.all()]
            self.repeated_data['id_set'] = [c.pk for c in self.initial['shipment'].containers.all()]
            self.repeated_data['kind_set'] = [c.kind.pk for c in self.initial['shipment'].containers.all()]
            self.fields['kind'].widget.attrs['readonly'] = True
            self.body.form_action = reverse_lazy(
                'shipment-add-containers',
                kwargs={'pk': self.initial['shipment'].pk}
            )
            self.body.title = 'Add Containers to Shipment'
            self.footer.set_buttons(
                Button('Save', type='submit', name="submit", value='submit', style='btn-primary'),
            )
        else:
            self.footer.set_buttons(
                Button("Continue", type="submit", value="Continue", style='btn-primary'),
            )

        self.body.layout = Layout(
            self.help_text(),
            Div(
                Row(
                    FullWidth(
                        Row(
                            HalfWidth('name'),
                            ThirdWidth(Field('kind', data_repeat_enable="true")),
                            SixthWidth(
                                Button(
                                    render_icon('minus'),
                                    style="btn-warning safe-remove mb-3"
                                ),
                                style="d-flex flex-column justify-content-end align-items-end"
                            ),
                            Div('shipment', 'id', css_class="d-none"),
                            style="repeat-row template g-2"
                        ),
                        style="repeat-group repeat-container"
                    ),
                    FullWidth(
                        Button(
                            f"{render_icon('plus')} Add Container", type="button",
                            style='btn-success add'
                        ),
                        style="mt-2"
                    ),
                    style="repeat-wrapper"
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
        cleaned_data = super().clean()
        for field in self.repeated_fields:
            if 'containers-{}'.format(field) in self.data:
                cleaned_data[f'{field}_set'] = self.data.getlist('containers-{}'.format(field))
            else:
                cleaned_data[f'{field}_set'] = self.data.getlist(field)
            self.fields[field].initial = cleaned_data[f'{field}_set']
        if not self.is_valid():
            for k, v in cleaned_data.items():
                if isinstance(v, list):
                    self.repeated_data[k] = [str(e) for e in v]
        return cleaned_data


class ShipmentGroupForm(ModalModelForm):
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
        super().__init__(*args, **kwargs)
        self.fields['name'].required = False
        self.body.title = "Create a Shipment"
        self.body.form_action = reverse_lazy("shipment-new")
        if self.initial.get('shipment'):
            groups = self.initial['shipment'].groups.order_by('priority')
            self.repeated_data = {
                'name_set': [str(group.name) for group in groups],
                'priority_set': [group.priority or 0 for group in groups],
                'id_set': [group.pk for group in groups],
                'comments_set': [group.comments or '' for group in groups]
            }

            self.footer.set_buttons(
                Button('Save', type='submit', name="submit", value='submit', style='btn-primary'),
            )

            self.body.title = "Add Groups to Shipment"
            self.body.form_action = reverse_lazy('shipment-add-groups', kwargs={'pk': self.initial['shipment'].pk})
        else:
            self.footer.set_buttons(
                Button(
                    'Fill Containers',
                    title='Auto-create one group per container (filled with samples) ignoring the groups defined above',
                    type='submit', name="submit", value='Fill', style='me-auto btn-warning'
                ),
                Button('Finish', type='submit', name="submit", value='Finish', style='btn-primary'),
            )

        self.body.layout = Layout(
            self.help_text(),
            Div(
                Row(
                    FullWidth(
                        Row(
                            QuarterWidth('name'),
                            HalfWidth('comments'),
                            QuarterWidth(
                                HTML(
                                    f'<a title="Drag to change group priority" '
                                    f'class="move btn btn-white">{render_icon("move")}</a>'
                                ),
                                Button(
                                    render_icon('minus'),
                                    style="btn-warning safe-remove",
                                    title="Delete Group",
                                ),
                                style="d-flex flex-row justify-content-end align-items-end mb-3 gap-2"
                            ),
                            Div(
                                Field('shipment'),
                                Field('priority'),
                                Field('id'),
                                id="group-details--{rowcount}"
                            ),
                            style="repeat-row template g-2"
                        ),
                        style="repeat-group repeat-container"
                    ),
                    FullWidth(
                        Button(
                            f"{render_icon('plus')} Add Group", type="button",
                            style='btn-success add'
                        ),
                        style="mt-2"
                    ),
                    style="repeat-wrapper"
                ),
                css_class='repeat'
            ),
        )

    def help_text(self):
        if self.initial.get('shipment'):
            return Div(
                HTML(
                    f'Add samples in new groups later from the shipment page. '
                    '<span class="text-danger">Removing a group will also remove any samples in the group</span>'
                ),
                css_class="alert alert-info mb-1"
            )
        else:
            return Div(
                HTML(
                    'Specify groups for similar samples. Groups names will be used as the prefix for sample names. '
                    f'Add samples from the shipment page after your shipment is created. '
                ),
                css_class="alert alert-info mb-1"
            )

    def clean(self):
        self.repeated_data = {}
        cleaned_data = super().clean()
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


class SSHKeyForm(ModalModelForm):
    class Meta:
        model = SSHKey
        fields = ['name', 'key', 'user']
        widgets = {
            'key': forms.Textarea(attrs={"placeholder": "SSH Public Key, begins with 'ssh-XXX'"}),
            'user': forms.HiddenInput()
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.body.layout = Layout(
            Row(
                'user',
                FullWidth('name'),
            ),
            Row(
                FullWidth('key'),
            ),
        )
        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )


class GuideForm(ModalModelForm):
    class Meta:
        model = Guide
        fields = ['title', 'description', 'kind', 'staff_only', 'modal', 'attachment', 'url', 'priority']
        widgets = {
            'description': forms.Textarea(attrs={"cols": 40, "rows": 7}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            self.body.title = "Edit Announcement"
            self.body.form_action = reverse_lazy('guide-edit', kwargs={'pk': self.instance.pk})
        else:
            self.body.title = "New Announcement"
            self.body.form_action = reverse_lazy('new-guide')
        self.body.layout = Layout(
            Row(
                SixthWidth('priority'),
                FiveSixthWidth('title'),
            ),
            Row(
                FullWidth('description'),
            ),
            Row(
                HalfWidth('kind'),
                HalfWidth(
                    Field('url', title="Resource examples:\n'youtube:<vid>' or \n'flickr:<album>:<photo>'")
                ),
            ),
            Row(
                FullWidth(Field('attachment')),
            ),
            Row(
                HalfWidth(
                    Div(
                        Field('staff_only', css_class="form-check-input"),
                        css_class="form-check form-switch"
                    )
                ),
                HalfWidth(
                    Div(
                        Field('modal', css_class="form-check-input"),
                        css_class="form-check form-switch"
                    )
                ),
            ),
        )
        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )


class UserEditForm(ModalModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone', 'default_project')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.body.title = _("Edit Profile")
            self.body.form_action = reverse_lazy('user-edit', kwargs={'username': self.instance.username})
            self.fields['default_project'].queryset = self.instance.get_projects()
        self.body.layout = Layout(
            Row(
                HalfWidth('first_name'),
                HalfWidth('last_name'),
                style="g-2"
            ),
            Row(
                HalfWidth('email'),
                HalfWidth(
                    Field(
                        'phone', pattern=r"(\+\d{1,3}-)?\d{3}-\d{3}-\d{4}( x\d+)?$",
                        placeholder="[+9-]999-999-9999[ x9999]"
                    )
                ),
                style="g-2"
            ),
            Row(
                FullWidth(Field('default_project', css_class='select')),
                style="g-2"
            ),
        )
        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )


class SystemSettingsForm(ModalModelForm):
    country = forms.ModelChoiceField(
        queryset=Country.objects.all(),
        required=False,
        empty_label=_("---------")
    )
    region = forms.ModelChoiceField(
        queryset=Region.objects.all(),
        required=False,
        empty_label=_("---------")
    )

    class Meta:
        model = SystemSettings
        fields = (
            'name', 'acronym', 'maintenance_mode', 'contact_person',
            'support_email', 'department', 'address', 'city',
            'region', 'country', 'postal_code', 'organisation', 'contact_phone'
        )
        widgets = {
            'shipping_notes': forms.Textarea(attrs={'rows': "2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        country_val = self.data.get('country') if self.data else (self.instance.country_id if self.instance and self.instance.pk else None)
        if hasattr(country_val, 'pk'):
            country_val = country_val.pk
        if country_val:
            try:
                self.fields['region'].queryset = Region.objects.filter(country_id=int(country_val))
            except (ValueError, TypeError):
                self.fields['region'].queryset = Region.objects.none()
        elif self.data and self.data.get('region'):
            self.fields['region'].queryset = Region.objects.all()
        else:
            self.fields['region'].queryset = Region.objects.none()

        self.body.title = _("Edit System Settings")
        self.body.layout = Layout(
            Row(
                ThreeQuarterWidth('name'), QuarterWidth('acronym'),
                style="g-2"
            ),
            Row(
                ThirdWidth('contact_person'),
                ThirdWidth('support_email'),
                ThirdWidth('contact_phone'),
                style="g-2"
            ),
            Row(
                HalfWidth('organisation'),
                HalfWidth('department'),
                style="g-2"
            ),
            Row(
                TwoThirdWidth('address'),
                ThirdWidth('city'),
                style="g-2"
            ),
            Row(
                ThirdWidth(Field('country', css_class='select')),
                ThirdWidth(Field('region', css_class='select')),
                ThirdWidth('postal_code'),
                style="g-2"
            ),
        )
        self.footer.set_buttons(
            Button('Revert', type='reset', value='Reset', style="btn-secondary"),
            Button('Save', type='submit', name="submit", value='submit', style='btn-primary'),
            HTML("""{% load static %}<script src="{% static 'lims/js/basiclive-countries.js' %}"></script>""")
        )

    def clean(self):
        cleaned_data = super().clean()
        country = cleaned_data.get('country')
        region = cleaned_data.get('region')
        if region:
            if not country:
                cleaned_data['country'] = region.country
            elif region.country_id != country.id:
                self.add_error('region', _("The selected region does not belong to the selected country."))
        return cleaned_data
