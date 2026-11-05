from datetime import timedelta
from pathlib import Path

from django.utils.csp import CSP

REPORTCRAFT_FUNCTIONS = [
    'basiclive.utils.functions.String',
    'basiclive.utils.functions.JoinArray',
    'basiclive.utils.functions.ArrayLength',
    'reportcraft.functions.postgres.Join',
    'django.contrib.postgres.aggregates.ArrayAgg',
    'django.contrib.postgres.aggregates.JSONBAgg',
    'basiclive.utils.functions.ArrayItems',
    'basiclive.utils.functions.JSONAvg',
    'basiclive.utils.functions.AgeYears',
    'basiclive.utils.functions.AgeMonths',
    'basiclive.utils.functions.YearMonth',
    'basiclive.utils.functions.Quarter',
    'basiclive.utils.functions.RootValue',
    'basiclive.utils.functions.SubMin',
    'basiclive.utils.functions.SubMax',
    'basiclive.utils.functions.SubCount',
    'basiclive.utils.functions.SubAvg',
    'basiclive.utils.functions.SubSum',
    'basiclive.utils.functions.Shifts',
    'basiclive.utils.functions.BoolMap',
    'basiclive.utils.functions.TruncateWords',
]

BASICLIVE_APPS = [
    "rest_framework",
    "crispy_forms",
    "crispy_bootstrap5",
    "crisp_modals",

    'itemlist',
    'reportcraft',
    'basiclive.core.lims',
    'basiclive.core.api',
    'basiclive.core.acl',
]
OPTIONAL_APPS = {
    'USE_CRM': 'basiclive.core.crm',
    'USE_SCHEDULE': 'basiclive.core.schedule',
    'USE_NOTEBOOKS': 'basiclive.core.notebooks',
    'USE_PUBLICATIONS': 'basiclive.core.publications',
}
REPORTCRAFT_APPS = ['lims', 'schedule', 'crm', 'publications', 'acl', 'notebooks']
REPORTCRAFT_MIXINS = {
    'VIEW': ['basiclive.utils.mixins.StaffRequiredMixin'],
    'EDIT': ['basiclive.utils.mixins.AdminRequiredMixin'],
}
SECURE_CSP = {
    "default-src": [
        CSP.SELF,
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com"
    ],
    "img-src": [
        "data:",
        CSP.SELF,
        "https://cdn.rcsb.org"
    ],
    "style-src": [
        CSP.SELF,
        CSP.UNSAFE_INLINE,
        "https://fonts.googleapis.com",
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com"
    ],
    "font-src": [
        CSP.SELF,
        "https://fonts.gstatic.com"
    ],
    "script-src": [
        CSP.UNSAFE_INLINE,
        CSP.UNSAFE_EVAL,
        CSP.SELF,
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com"
    ],
    "frame-src": [
        CSP.NONE
    ],
}

EXTRA_SETTINGS = {
    "CRISPY_ALLOWED_TEMPLATE_PACKS": "bootstrap5",
    "CRISPY_TEMPLATE_PACK": "bootstrap5",
    'REPORTCRAFT_FUNCTIONS': REPORTCRAFT_FUNCTIONS,
    'REPORTCRAFT_MIXINS': REPORTCRAFT_MIXINS,
    'SECURE_CSP': SECURE_CSP,
    'AUTH_USER_MODEL': 'lims.User',
    "BASICLIVE_ICON_BACKEND": "basiclive.core.lims.icons.ThemifyBackend",
    "REST_FRAMEWORK": {
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'rest_framework_simplejwt.authentication.JWTAuthentication',
        )
    },
    "SIMPLE_JWT": {
        # "X-Access-Token" works better as it's not removed by earlier middleware in the client request
        "AUTH_HEADER_NAME": "HTTP_X_ACCESS_TOKEN",
        "ACCESS_TOKEN_LIFETIME": timedelta(days=7),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=365),
    }
}


def configure(settings: dict) -> None:
    """
    Called from the bottom of Django settings.py file. Loads local.settings, uses it to
    override main settings, then process it to update installed apps and other settings
    with pre-requisites needed for BasicLive to function properly.

    :param settings: settings dictionary, use globals() from within settings.py
    """

    # Configure ReportCraft, REST Framework, and other BasicLive settings
    settings.update(EXTRA_SETTINGS)

    # Update static and assets roots
    project_statics = Path(settings['PROJECT_DIR']) / 'static'
    assets_root = project_statics / 'assets'
    static_root = Path(settings['BASE_DIR']) / 'static'
    media_root = Path(settings['BASE_DIR']) / 'local' / 'media'

    settings.update({
        "STATIC_ROOT": static_root,
        "STATICFILES_DIRS": [project_statics, assets_root],
        "MEDIA_ROOT": media_root,
    })

    try:
        import local.settings as local_settings
    except ModuleNotFoundError:
        print('local.settings not found, using default settings')
    else:
        settings.update({
            key: val
            for key, val in vars(local_settings).items()
            if not key.startswith('_') and not callable(val)
        })

    # Use a dictionary to ensure unique ordered list of apps
    installed_apps = dict.fromkeys(BASICLIVE_APPS)

    # Add optional apps to installed apps if configured
    # Optional apps are included by default
    lims_config = settings.get("BASICLIVE_LIMS", {})
    for toggle, app_name in OPTIONAL_APPS.items():
        if lims_config.get(toggle, True):
            installed_apps[app_name] = toggle

    # Add authentication apps
    if settings.get("BASICLIVE_AUTH_PROVIDERS", []):
        if "AUTHENTICATION_BACKENDS" not in settings:
            settings["AUTHENTICATION_BACKENDS"] = ['django.contrib.auth.backends.ModelBackend']
        for provider in settings["BASICLIVE_AUTH_PROVIDERS"]:
            if provider == 'ldap':
                settings["AUTHENTICATION_BACKENDS"].append('django_python3_ldap.auth.LDAPBackend')
            elif provider == 'cas':
                settings["AUTHENTICATION_BACKENDS"].append('django_cas_ng.backends.CASBackend')

    # Update INSTALLED APPS with unique app names in order
    settings["INSTALLED_APPS"].extend([
        name for name in installed_apps.keys() if name not in settings["INSTALLED_APPS"]
    ])

    # Update middlewares
    settings["MIDDLEWARE"].insert(0, 'basiclive.core.acl.middleware.TrustedAccessMiddleware')
    settings['MIDDLEWARE'].extend([
        'basiclive.core.api.middleware.APIAuthenticationMiddleware',
        'basiclive.core.lims.middleware.ProjectContextMiddleware',
    ])



