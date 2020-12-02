from django.conf import settings


def version_context_processor(request):
    """
    Version context processor
    """
    return {'version': settings.APP_VERSION}

