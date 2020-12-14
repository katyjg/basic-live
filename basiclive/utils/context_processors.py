from basiclive import version


def version_context_processor(request):
    """
    Version context processor
    """
    return {'version': version.get_version()}

