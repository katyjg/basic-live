from typing import Any

from basiclive.utils.conf import AppSettings

DEFAULTS: dict[str, Any] = {
    "BASE_DN": "dc=demo1,dc=freeipa,dc=org",
    "SERVER_URI": "ipa.demo1.freeipa.org",
    "MANAGER_DN": None,
    "MANAGER_SECRET": None,
    "USER_TABLE": "ou=People",
    "USER_ROOT": "/home",
    "GROUP_TABLE": "ou=Groups",
    "USER_SHELL": "/bin/bash",
    "WORDS_DICTIONARY": "/usr/share/dict/words",
    "PASSPHRASE_SEPARATORS": " -/",
    "MANAGE_DIRECTORY": False,
    "SEND_EMAILS": False,
    "ADMIN_UIDS": [2000],
    "AUTH_URL": "ldap://ipa.demo1.freeipa.org:389",
    "AUTH_SEARCH_BASE": "ou=Peopledc=demo1,dc=freeipa,dc=org",
    "AUTH_OBJECT_CLASS": "posixAccount",
    "AUTH_USER_LOOKUP_FIELDS": ("username",),
    "AUTH_USE_TLS": True,
    "AUTH_USER_FIELDS": {
        "username": "uid",
        "first_name": "givenName",
        "last_name": "sn",
        "email": "mail",
    },
}

settings = AppSettings("LDAP", DEFAULTS)
