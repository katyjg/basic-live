from django import template
from django.utils import timezone
from datetime import datetime, timedelta
from django.conf import settings

register = template.Library()

HOURS_PER_SHIFT = getattr(settings, 'HOURS_PER_SHIFT', 8)

@register.simple_tag
def save_time(t):
    return t

@register.filter
def check_time(modified, last):
    if not last:
        return True
    return modified > (last + timedelta(minutes=15))

@register.filter
def duration_shifts(td):
    return int(td.total_seconds() // 3600 / HOURS_PER_SHIFT)