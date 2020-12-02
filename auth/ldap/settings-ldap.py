AUTH_MODULE = 'auth.ldap'
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'django_python3_ldap.auth.LDAPBackend'
]
# LDAP Server Settings
LDAP_BASE_DN = 'dc=demo1,dc=freeipa,dc=org'
LDAP_SERVER_URI = 'ipa.demo1.freeipa.org'
LDAP_MANAGER_DN = 'cn=Directory Manager'
LDAP_MANAGER_SECRET = SECRET_KEY
LDAP_USER_TABLE = 'ou=People'
LDAP_USER_ROOT = '/home'
LDAP_GROUP_TABLE = 'ou=Groups'
LDAP_USER_SHELL ='/bin/bash'
LDAP_SEND_EMAILS = False
LDAP_ADMIN_UIDS = [2000]

# LDAP Authentication Settings
LDAP_AUTH_URL = "ldap://{}:389".format(LDAP_SERVER_URI)
LDAP_AUTH_SEARCH_BASE = "{}{}".format(LDAP_USER_TABLE, LDAP_BASE_DN)
LDAP_AUTH_OBJECT_CLASS = "posixAccount"
LDAP_AUTH_USER_LOOKUP_FIELDS = ("username",)
LDAP_AUTH_USE_TLS = True
LDAP_AUTH_USER_FIELDS = {
    "username": "uid",
    "first_name": "givenName",
    "last_name": "sn",
    "email": "mail",
}


def clean_user(user, data):
    # A function to clean up user data from ldap information

    names = data['gecos'][0].split(' ', 1)
    first_name = names[0].strip()
    last_name = "" if len(names) < 2 else names[1].strip()
    email = data.get('mail', [''])[0]
    user_uids = set(map(int, data['gidnumber']))
    admin_uids = set(map(int, LDAP_ADMIN_UIDS))

    if user_uids & admin_uids:
        user.is_superuser = True
        user.is_staff = True

    if not user.name:
        user.name = user.username

    if (first_name, last_name, email) != (user.first_name, user.last_name, user.email):
        user.first_name = first_name
        user.last_name = last_name
        user.email = email
    user.save()


LDAP_AUTH_SYNC_USER_RELATIONS = clean_user
