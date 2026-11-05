
import basiclive
from basiclive.core.lims.conf import settings as lims_settings
from basiclive.core.schedule.conf import settings as schedule_settings


def export_settings(request):
    """
    Export some settings to the template context for use in templates.
    :param request: The HTTP request object.
    :return: A dictionary containing the exported settings.
    """
    return {
        'APP_VERSION': lims_settings.APP_VERSION,
        'BASIC_LIVE_VERSION': basiclive.__version__,
        'APP_NAME': lims_settings.APP_NAME,
        'USE_SCHEDULE': lims_settings.USE_SCHEDULE,
        'USE_PUBLICATIONS': lims_settings.USE_PUBLICATIONS,
        'USE_CRM': lims_settings.USE_CRM,
        'USE_ACL': lims_settings.USE_ACL,
        'USE_NOTEBOOKS': lims_settings.USE_NOTEBOOKS,
        'SUPPORT_EMAIL': lims_settings.SUPPORT_EMAIL,
        'MIN_SUPPORT_HOUR': schedule_settings.MIN_SUPPORT_HOUR,
        'MAX_SUPPORT_HOUR': schedule_settings.MAX_SUPPORT_HOUR,
    }
