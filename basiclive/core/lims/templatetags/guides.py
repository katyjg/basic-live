import re
from django.template import Library
from django.urls import reverse
import mimetypes

from basiclive.core.lims import models

register = Library()


@register.inclusion_tag('lims/guides.html', takes_context=True)
def load_guides(context):
    return {
        'guides': models.Guide.objects.all(),
        'request': context
    }


# maps url names to regex for generating parameter values from the guide url field value
# Examples:
#   youtube - "youtube:u2-SdXDI1gs"
#   flickr  - "flickr:97079436@N04:49122723877_3af6c8ebd9_k.jpg"
EMBED_URLS = {
    'guide-youtube': re.compile(r'^youtube:(?P<video>[\w-]{11})$'),
    'guide-flickr': re.compile(r'^flickr:(?P<album>[^:]*):(?P<photo>[^:]*)$'),
}


@register.simple_tag
def guide_link(guide):
    """
    Converts a Guide url magic phrase into a url for embedding into a modal
    :param guide: Guide object
    :return:  An expanded url string or the original string if nothing matches
    """

    if guide.url:
        parameters = {'pk': guide.pk}
        for url_name, pattern in EMBED_URLS.items():
            m = pattern.match(guide.url)
            if m:
                parameters.update(m.groupdict())
                return reverse(url_name, kwargs=parameters)
        return guide.url
    elif guide.has_image():
        return reverse('guide-image', kwargs={'pk': guide.pk})
    elif guide.has_video():
        return reverse('guide-video', kwargs={'pk': guide.pk})
    else:
        return "#!"


@register.filter
def mime_type(field):
    if field:
        return mimetypes.guess_type(field.url)[0]
    else:
        return ""