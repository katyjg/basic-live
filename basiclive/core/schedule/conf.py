from basiclive.utils.conf import AppSettings

DEFAULTS = {
    "HOURS_PER_SHIFT": 8,
    "SCHEDULE_PROVIDER": None,
    "MIN_SUPPORT_HOUR": 0,
    "MAX_SUPPORT_HOUR": 24,
    "APP_NAME": "basiclive",
    "FROM_EMAIL": "sender@no-reply.ca",
    "USE_PUBLICATIONS": True,
}

settings = AppSettings("SCHEDULE", DEFAULTS)
