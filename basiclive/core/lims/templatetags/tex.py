from django.template.defaultfilters import stringfilter
from django import template
from django.conf import settings

register = template.Library()

@register.filter
@stringfilter
def texsafe(value):
    """ Returns a string with LaTeX special characters stripped/escaped out """
    special = [
    [ "\\xc5", 'A'],       #'\\AA'
    [ "\\xf6", 'o'],
    [ "&", 'and'],        #'\\"{o}'
    ]
    for char in ['\\', '^', '~', '%', "'", '"']: # these mess up things
        value = value.replace(char, '')
    for char in ['#','$','_', '{', '}', '<', '>']: # these can be escaped properly
        value = value.replace(char, '\\' + char)
    for char, new_char in special:
        value = eval(repr(value).replace(char, new_char))
    return value

@register.simple_tag
def path_to_files():
    return getattr(settings, "BASE_DIR", "/tmp")
