import base64
import re
import uuid

from crisp_modals.forms import (
    Button,
    FullWidth,
    ModalModelForm,
    Row,
)
from crispy_forms.layout import Hidden, Layout
from django import forms
from django.core.files.base import ContentFile
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from .models import Entry, Notebook
from .utils import clean_json


class NotebookForm(ModalModelForm):
    class Meta:
        model = Notebook
        fields = [
            'title',
            'description',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if self.instance.pk and not self.instance._state.adding:
            self.body.title = _("Edit Notebook")
            if not getattr(self.body, 'form_action', None):
                try:
                    self.body.form_action = reverse_lazy('notebooks:notebook-edit', kwargs={'pk': self.instance.pk})
                except Exception:
                    pass
        else:
            self.body.title = _("Create Notebook")
            if not getattr(self.body, 'form_action', None):
                try:
                    self.body.form_action = reverse_lazy('notebooks:create-notebook')
                except Exception:
                    pass

        self.body.layout = Layout(
            Row(
                FullWidth('title'),
                FullWidth('description'),
                style="g-2",
            )
        )
        self.footer.set_buttons(
            Button('Cancel', type='button', value='cancel', style="btn-secondary", data_bs_dismiss="modal"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )


class EntryForm(ModalModelForm):
    tags = forms.CharField(
        label=_('Tags'),
        required=False,
        widget=forms.TextInput(attrs={'placeholder': _('e.g. sample, calibration, run-1')}),
        help_text=_('Comma- or semicolon-separated tags'),
    )

    class Meta:
        model = Entry
        fields = ['tags']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.notebook = kwargs.pop('notebook', None)
        self.kind = kwargs.pop('kind', None)
        super().__init__(*args, **kwargs)

        if self.instance.pk and self.instance.tags:
            self.initial['tags'] = ', '.join(self.instance.tags)

        self.footer.set_buttons(
            Button('Cancel', type='button', value='cancel', style="btn-secondary", data_bs_dismiss="modal"),
            Button('Save', type='submit', name="submit", value='save', style='btn-primary'),
        )

    def clean_tags(self):
        raw_tags = self.cleaned_data.get('tags', '')
        if isinstance(raw_tags, str):
            return [t.strip() for t in re.split(r'[,;]', raw_tags) if t.strip()]
        return raw_tags or []

    def save(self, commit=True):
        entry = super().save(commit=False)
        if 'tags' in self.cleaned_data:
            entry.tags = self.cleaned_data['tags']
        if not entry.pk:
            if self.user and not entry.author_id:
                entry.author = self.user
            if self.notebook and not entry.notebook_id:
                entry.notebook = self.notebook
            if self.kind and not entry.kind_id:
                entry.kind = self.kind
        if commit:
            entry.save()
            self.save_m2m()
        return entry


class TextEntryForm(EntryForm):
    class Meta(EntryForm.Meta):
        fields = ['text', 'tags']
        widgets = {
            'text': forms.Textarea(attrs={
              'rows': 10,
              'id': 'entry-text-editor',
              'placeholder': _('Write notes using Markdown and LaTeX...')
            }),
        }
        labels = {
            'text': _('Content'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        is_edit = bool(self.instance.pk and not self.instance._state.adding)
        self.body.title = _("Edit Text Entry") if is_edit else _("Create Text Entry")
        self.body.layout = Layout(
            Row(
                FullWidth('text'),
                FullWidth('tags'),
                style="g-2",
            )
        )


class ImageEntryForm(EntryForm):
    file = forms.FileField(
        label=_('Image File'),
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': 'image/*', 'class': 'd-none dropzone-target'}),
    )

    class Meta(EntryForm.Meta):
        fields = ['file', 'text', 'tags']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3, 'placeholder': _('Optional caption or notes...')}),
        }
        labels = {
            'text': _('Caption'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        is_edit = bool(self.instance.pk and not self.instance._state.adding)
        self.body.title = _("Edit Image Entry") if is_edit else _("Create Image Entry")
        self.body.layout = Layout(
            Row(
                FullWidth('file'),
                FullWidth('text'),
                FullWidth('tags'),
                style="g-2",
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        if 'file' not in self.errors:
            has_file = cleaned_data.get('file') or (self.instance.pk and self.instance.file)
            if not has_file and not self.instance.pk:
                self.add_error('file', _('An image file is required.'))
        return cleaned_data


class VideoEntryForm(EntryForm):
    file = forms.FileField(
        label=_('Video File'),
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': 'video/*', 'class': 'd-none dropzone-target'}),
    )

    class Meta(EntryForm.Meta):
        fields = ['file', 'text', 'tags']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3, 'placeholder': _('Optional caption or notes...')}),
        }
        labels = {
            'text': _('Caption'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        is_edit = bool(self.instance.pk and not self.instance._state.adding)
        self.body.title = _("Edit Video Entry") if is_edit else _("Create Video Entry")
        self.body.layout = Layout(
            Row(
                FullWidth('file'),
                FullWidth('text'),
                FullWidth('tags'),
                style="g-2",
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        if 'file' not in self.errors:
            has_file = cleaned_data.get('file') or (self.instance.pk and self.instance.file)
            if not has_file and not self.instance.pk:
                self.add_error('file', _('A video file is required.'))
        return cleaned_data


class SketchEntryForm(EntryForm):
    sketch_data = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'sketch-data-input'}),
    )
    file = forms.FileField(
        label=_('Sketch Image'),
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': 'image/*', 'class': 'd-none'}),
    )

    class Meta(EntryForm.Meta):
        fields = ['file', 'sketch_data', 'text', 'tags']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 2, 'placeholder': _('Optional sketch notes...')}),
        }
        labels = {
            'text': _('Notes'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        is_edit = bool(self.instance.pk and not self.instance._state.adding)
        self.body.title = _("Edit Sketch Entry") if is_edit else _("Create Sketch Entry")
        self.body.layout = Layout(
            Row(
                Hidden('sketch_data', ''),
                FullWidth('file'),
                FullWidth('text'),
                FullWidth('tags'),
                style="g-2",
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        sketch_data = (cleaned_data.get('sketch_data') or '').strip()
        uploaded_file = cleaned_data.get('file')

        if sketch_data and sketch_data.startswith('data:image'):
            try:
                format_prefix, img_str = sketch_data.split(';base64,', 1)
                ext = format_prefix.split('/')[-1] if '/' in format_prefix else 'png'
                data = base64.b64decode(img_str)
                filename = f"sketch-{uuid.uuid4().hex[:8]}.{ext}"
                cleaned_data['file'] = ContentFile(data, name=filename)
            except Exception:
                self.add_error('sketch_data', _('Invalid sketch image data.'))
        elif not uploaded_file and not (self.instance.pk and self.instance.file):
            if not self.instance.pk and 'file' not in self.errors:
                self.add_error('file', _('A sketch drawing or image is required.'))
        return cleaned_data


class DataEntryForm(EntryForm):
    class Meta(EntryForm.Meta):
        fields = ['text', 'tags']
        widgets = {
            'text': forms.Textarea(attrs={
                'rows': 10,
                'id': 'entry-data-editor',
                'placeholder': _('JSON data or tabular payload...')
            }),
        }
        labels = {
            'text': _('Data (JSON)'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        is_edit = bool(self.instance.pk and not self.instance._state.adding)
        self.body.title = _("Edit Data Entry") if is_edit else _("Create Data Entry")
        self.body.layout = Layout(
            Row(
                FullWidth('text'),
                FullWidth('tags'),
                style="g-2",
            )
        )

    def clean_text(self):
        raw_text = self.cleaned_data.get('text', '')
        if raw_text:
            try:
                return clean_json(raw_text)
            except Exception as e:
                raise forms.ValidationError(_('Invalid JSON format: %(error)s'), params={'error': str(e)})
        return raw_text


class FileEntryForm(EntryForm):
    file = forms.FileField(
        label=_('Attachment File'),
        required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'dropzone-target'}),
    )

    class Meta(EntryForm.Meta):
        fields = ['file', 'text', 'tags']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 3, 'placeholder': _('Optional file description...')}),
        }
        labels = {
            'text': _('Description'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        is_edit = bool(self.instance.pk and not self.instance._state.adding)
        self.body.title = _("Edit File Entry") if is_edit else _("Create File Entry")
        self.body.layout = Layout(
            Row(
                FullWidth('file'),
                FullWidth('text'),
                FullWidth('tags'),
                style="g-2",
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        if 'file' not in self.errors:
            has_file = cleaned_data.get('file') or (self.instance.pk and self.instance.file)
            if not has_file and not self.instance.pk:
                self.add_error('file', _('A file upload is required.'))
        return cleaned_data


class TagsForm(EntryForm):
    class Meta(EntryForm.Meta):
        model = Entry
        fields = ['tags']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.body.title = _("Edit Tags")
        self.body.layout = Layout(
            Row(
                FullWidth('tags'),
                style="g-2",
            )
        )


ENTRY_FORMS = {
    'text': TextEntryForm,
    'image': ImageEntryForm,
    'video': VideoEntryForm,
    'sketch': SketchEntryForm,
    'data': DataEntryForm,
    'file': FileEntryForm,
}


def get_entry_form_class(kind):
    """
    Return the corresponding EntryForm subclass for an EntryType name or kind string.
    :param kind: str or EntryType instance
    :return: EntryForm subclass or None
    """
    if hasattr(kind, 'name'):
        kind_key = kind.name.lower()
    elif isinstance(kind, str):
        kind_key = kind.lower()
    else:
        return None
    return ENTRY_FORMS.get(kind_key)
