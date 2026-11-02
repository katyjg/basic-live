from basiclive.utils.conf import AppSettings

DEFAULTS = {
    "APP_NAME": "BasicLIVE",
    "APP_VERSION": "0.0.0",
    "SUPPORT_EMAIL": "support@lightsource.ca",
    "USE_SCHEDULE": True,
    "USE_ACL": True,
    "USE_CRM": True,
    "USE_PUBLICATIONS": True,
    "USE_NOTEBOOKS": True,
    "DOWNLOAD_PROXY_URL": "http://basiclive.core-data/download",
    "MAX_CONTAINER_DEPTH": 2,
    "RESTRICT_DOWNLOADS": False,
    "KEEP_ACTIVITY_WEEKS": 104,  # 2 years
    "SIMULATED_SESSION_LIFETIME_DAYS": 30,  # 30 days
    "LOADER_SELECT_DURATION": 5 * 60,  # 5 minutes
    "RESTRUCTUREDTEXT_FILTER_SETTINGS": {},
    "SEND_EMAILS": False,
    "BASE_DIR": "/tmp",
    "PROJECT_PROVIDER": None,
}

settings = AppSettings("LIMS", DEFAULTS)
