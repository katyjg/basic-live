import json
import time

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

from ..models import EntryType
from ..utils import clean_json, simpletime, timeish

register = template.Library()


@register.simple_tag(takes_context=True)
def get_entry_types(context):
    return EntryType.objects.all()


@register.simple_tag(takes_context=True)
def show_entry(context, entry):
    entry_template = template.loader.get_template(f'notebooks/entries/{entry.kind.name.lower()}.html')
    ctx = {}
    ctx.update(context.flatten())
    ctx['entry'] = entry
    return mark_safe(entry_template.render(ctx))


@register.filter(name='json')
def dump_data(data):
    return mark_safe(json.dumps(data))


@register.simple_tag(takes_context=False)
def load_data(entry):
    info = json.loads(entry.text)
    return {
        'headers': info['headers'],
        'data': [
            [info['data'][str(j)][i] for j, key in enumerate(info['headers'])]
            for i in range(len(info['data']["0"]))
        ],
    }


@register.simple_tag(takes_context=False)
def plot_axes(entry):
    data = json.loads(entry.text)
    plots = []
    for i, vals in data.get('data', {}).items():
        if any(isinstance(e, (float, int)) for e in vals):
            plots.append(data['headers'][int(i)])
    return plots


@register.simple_tag(takes_context=True)
def nocache_static(context, debug_only=True):
    if (debug_only and settings.DEBUG) or not debug_only:
        ts = time.time()
        return f'?ts={int(ts)}'
    return ""


@register.filter(name='timeish')
def do_timeish(dt):
    return mark_safe(timeish(dt))


@register.filter(name='simpletime')
def do_simpletime(dt):
    return mark_safe(simpletime(dt))


@register.filter(name='is_editable_by')
def is_editable_by(obj, user):
    return obj.can_edit(user)


@register.filter(name='clean_json')
def do_clean(text):
    return mark_safe(clean_json(text))


