from django import template
from django.utils.safestring import mark_safe
import json
import numpy
register = template.Library()


def convert(o):
    if isinstance(o, numpy.int64):
        return int(o)
    elif isinstance(o, numpy.float64):
        return int(0)
    elif isinstance(o, numpy.ndarray):
        return o.tolist()
    raise TypeError


@register.filter
def jsonify(data):
    return mark_safe(json.dumps(data, default=convert))

