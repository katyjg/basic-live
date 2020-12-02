import os
import time

from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag
def get_setting(key, default=""):
    return getattr(settings, key, default)