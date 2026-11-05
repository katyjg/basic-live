from django.template import Library

register = Library()


@register.simple_tag(name='status_theme')
def status_theme(state, default="", **kwargs) -> str:
    """
    Returns the key from kwargs that matches the given state. Can be used to map a state to a specific tag or label.
    If no match is found, it returns the default value.
    :param state: value to match against the values in kwargs.
    :param default: default string to return if no match is found.
    :param kwargs: key-value pairs where keys are the tags and values are the states.
    """

    for key, value in kwargs.items():
        if value == state:
            return key
    return default
