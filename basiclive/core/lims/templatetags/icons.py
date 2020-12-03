from django.template import Library

register = Library()


@register.inclusion_tag('lims/components/icon-info.html')
def show_icon(label='', icon='', badge=None, color='', tooltip='', show_null=False):
    badge = None if not badge and not show_null else badge
    return {
        'label': label,
        'icon': icon,
        'badge': badge,
        'color': color,
        'tooltip': tooltip
    }