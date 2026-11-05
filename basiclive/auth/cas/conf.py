from typing import Any

from basiclive.utils.conf import AppSettings

DEFAULTS: dict[str, Any] = {
    "SERVER_URL": "https://cas-test.clsi.ca/",
    "SERVICE_DESCRIPTION": "LIVE",
    "LOGOUT_COMPLETELY": True,
    "CREATE_USER": True,
    "REDIRECT_URL": "login",
    "LOGIN_URL_NAME": "login",
    "LOGOUT_URL_NAME": "logout",
}

settings = AppSettings("CAS", DEFAULTS)
