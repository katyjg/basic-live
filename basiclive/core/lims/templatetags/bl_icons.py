
import os
import re
from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe
from django.template import Library

from basiclive.core.lims.icons import get_icon_backend

register = Library()


@register.inclusion_tag('lims/components/icon-info.html')
def show_icon(
    label='',
    icon='',
    badge=None,
    size=None,
    color=None,
    tooltip='',
    show_null=False,
    extra_class=''
):
    badge = None if not badge and not show_null else badge
    backend = get_icon_backend()
    icon_class = backend.get_css_classes(icon=icon, size=size, extra_class=extra_class) if icon else ''

    return {
        'label': label,
        'icon': icon_class,
        'icon_class': icon_class,
        'badge': badge,
        'color': color,
        'size': size,
        'tooltip': tooltip,
        'extra_class': extra_class,
    }


@register.simple_tag
def show_icon_css():
    """
    Renders <link rel="stylesheet" ...> tags for the active icon backend stylesheets.
    """
    backend = get_icon_backend()
    urls = backend.get_stylesheet_urls()
    links = []
    for url in urls:
        if not url:
            continue
        href = url if url.startswith(('http://', 'https://', '/')) else static(url)
        links.append(f'<link rel="stylesheet" href="{href}">')
    return mark_safe('\n'.join(links))


@register.simple_tag
def render_svg_icon(icon_name, extra_class=""):
    """
    Renders a lightweight HTML <svg> snippet that points to the sprite.
    Allows for dynamic scaling and hover handling.
    """
    return mark_safe(
        f"""
        <svg class="hover-icon {extra_class}" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
            <use href="#icon-{icon_name}"></use>
        </svg>
    """
    )


@register.simple_tag
def compile_svg_sprite(icon_list_string):
    """
    Compiles a string list of icon names into a single hidden SVG sprite snippet.
    Example: {% compile_svg_sprite "heart search settings user" %}
    """
    icon_names = icon_list_string.split()
    sprite_content = ['<svg xmlns="http://w3.org" style="display: none;">']

    # Locate where you keep your raw icon SVGs (e.g., in a static folder)
    svg_dir = os.path.join(settings.BASE_DIR, 'static', 'icons')

    for name in icon_names:
        file_path = os.path.join(svg_dir, f"{name}.svg")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

                # Strip out the wrapper <svg> tags and convert to a <symbol>
                # This makes the asset universally reusable via <use>
                inner_content = re.sub(r'<svg[^>]*>', '', content).replace('</svg>', '')
                sprite_content.append(f'<symbol id="icon-{name}" viewBox="0 0 24 24">{inner_content}</symbol>')

    sprite_content.append('</svg>')
    return mark_safe('\n'.join(sprite_content))


@register.simple_tag
def get_activity_icon(activity):
    """
    Returns the icon name for a given activity type.
    """
    activity_icon_map = {
        0: 'user',
        1: 'user-off',
        2: 'task',
        3: 'add',
        4: 'edit',
        5: 'trash',
        6: 'archive',
        # Add more mappings as needed
    }
    return activity_icon_map.get(activity.action_type, 'question')