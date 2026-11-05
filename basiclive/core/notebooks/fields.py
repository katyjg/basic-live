import re
from collections.abc import Sequence

from django import forms
from django.db import models

STRING_LIST_PATTERN = re.compile(r"<([^><]+)>")
FORM_FIELD_SPLITTER = re.compile(r"[,;<>]+")


class StringListField(models.TextField):
    description = "A field to store a list of strings in the database. '<' or '>' not allowed within strings"

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        if value is None:
            return []
        if not isinstance(value, str):
            return value
        return STRING_LIST_PATTERN.findall(value)

    def get_prep_value(self, value):
        if isinstance(value, (list, tuple, set)):
            return "".join([f"<{str(v).strip()}>" for v in value])
        return ""

    def value_to_string(self, obj):
        value = self.value_from_object(obj)
        return self.get_prep_value(value)

    def get_prep_lookup(self, lookup_type, value):
        if isinstance(value, (list, tuple, set)):
            return self.get_prep_value(value)
        elif isinstance(value, str):
            return value.strip()
        return str(value)

    def formfield(self, **kwargs):
        defaults = {'form_class': DelimitedTextFormField}
        defaults.update(kwargs)
        return super().formfield(**defaults)


class DelimitedTextFormField(forms.CharField):
    widget = forms.TextInput

    def to_python(self, value):
        value = super().to_python(value)
        if not value:
            return []
        return list(filter(None, [v.strip() for v in FORM_FIELD_SPLITTER.split(value)]))

    def prepare_value(self, value):
        if isinstance(value, Sequence) and not isinstance(value, str):
            return "; ".join(value)
        return value

    def clean(self, value):
        return self.to_python(value)
