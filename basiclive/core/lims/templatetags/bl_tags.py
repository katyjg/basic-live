import json
from datetime import timedelta

import numpy
from django import template
from django.utils.safestring import mark_safe

from basiclive.utils.functions import get_hours_per_shift
from basiclive.utils.misc import natural_seconds

register = template.Library()


@register.filter
def duration_shifts(td):
    return int(td.total_seconds() // 3600 / get_hours_per_shift())


@register.simple_tag
def filter_reports(sample, session=None):
    return sample.reports(session=session)


@register.simple_tag(takes_context=True)
def prep_messages(context):
    msgs = context.get('messages', [])
    output = []
    if msgs:
        output= [
            {
                'text': msg.message,
                'tags': msg.tags,
                'type': msg.level,
            }
            for msg in msgs
        ]
    return mark_safe(json.dumps(output))


@register.filter
def verbose_name(value):
    return value._meta.verbose_name


@register.filter
def get_item(d, key):
    return d


PLANCK = 4.13566733e-15  # eV.s
LIGHT_SPEED = 299792458e10    # A/s


@register.filter("energy_to_wavelength")
def energy_to_wavelength(energy):
    """Convert energy in keV to wavelength in angstroms."""
    energy = float(energy)
    if energy == 0.0:
        return 0.0
    return (PLANCK * LIGHT_SPEED)/(energy * 1000.0)


@register.filter("humanize_duration")
def humanize_duration(duration, sec=False):
    if isinstance(duration, (int, float)):
        return natural_seconds(timedelta(hours=duration).total_seconds())
    elif isinstance(duration, timedelta):
        return natural_seconds(duration.total_seconds())
    else:
        return str(duration)


@register.filter("natural_duration")
def natural_duration(delta):
    return natural_seconds(delta.total_seconds())


@register.filter("human_number")
def human_number(value):
    """Comma formatted numbers."""
    return f"{value:,}"


@register.filter("human_code")
def human_code(text, length=None):
    """Comma formatted numbers."""
    if not text:
        return "-"
    elif not isinstance(text, str):
        text = str(text)

    text = text.replace(' ', '')
    if length and len(text) < length:
        text = text.zfill(length)

    n = len(text)
    # Handle base cases where string is too short to follow the rule
    if n <= 2 or n == 5:
        return text

    rem = n % 3
    num_4 = 0 if rem == 0 else (1 if rem == 1 else 2)
    num_3 = (n - (4 * num_4)) // 3

    # Build the list of split points based on chunk sizes (3s first, then 4s)
    indices = [0] + list(numpy.cumsum([3] * num_3 + [4] * num_4))
    parts = [text[i:j] for i, j in zip(indices[:-1], indices[1:] + [None])]
    return '-'.join(parts)


class NumpyEncoder(json.JSONEncoder):
    """Custom encoder to convert NumPy types into standard Python types."""
    def default(self, obj):
        if isinstance(obj, numpy.integer):
            return int(obj)
        elif isinstance(obj, numpy.floating):
            return float(obj)
        elif isinstance(obj, numpy.ndarray):
            return obj.tolist()
        return super().default(obj)


@register.filter
def jsonify(data):
    return mark_safe(json.dumps(data, cls=NumpyEncoder))


@register.filter
def can_edit(user, obj):
    """Check if a user can edit an object."""
    if not user.is_authenticated:
        return False
    if hasattr(obj, 'can_edit'):
        return obj.can_edit(user)
    return False


@register.filter
def can_view(user, obj):
    """Check if a user can view an object."""
    if not user.is_authenticated:
        return False
    if hasattr(obj, 'can_view'):
        return obj.can_view(user)
    return False


@register.filter
def is_member(user, project):
    """Check if a user is a member of the project"""
    if not user.is_authenticated:
        return False
    if hasattr(project, 'is_member'):
        return project.is_member(user)
    return False


@register.filter
def is_owner(user, project):
    """Check if a user is the owner of the project"""
    if not user.is_authenticated:
        return False
    if hasattr(project, 'is_owner'):
        return project.is_owner(user)
    return False
