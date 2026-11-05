from basiclive.utils.conf import AppSettings

DEFAULTS = {
    "TRUSTED_IPS": ["127.0.0.1/32"],
    "TRUSTED_URLS": ['^/json', '^/api'],
    "TRUSTED_PROXIES": 2,
    "MAX_OPEN_AGE": 30  # Maximum time in days for connections to be open before they are closed automatically
}

settings = AppSettings("ACL", DEFAULTS)
