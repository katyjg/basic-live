from django import template
from memoize import memoize

register = template.Library()


@memoize(timeout=3600)
def get_kind_col(container):
    kind = container.kind
    height = kind.height
    envelope = kind.envelope
    if envelope == 'circle' or (envelope == 'rect' and height >= 0.75):
        return 'col-3'
    else:
        return 'col-6'


@register.simple_tag
def container_col(container):
    return get_kind_col(container)


@register.filter
def container_samples(container, group):
    return container.samples.filter(group=group).count()