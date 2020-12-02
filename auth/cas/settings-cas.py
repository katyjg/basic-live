# Add 'django_cas_ng' to INSTALLED_APPS
# Add 'django_cas_ng.middleware.CASMiddleware' to MIDDLEWARE
AUTH_MODULE = 'auth.cas'
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'django_cas_ng.backends.CASBackend'
]
# CAS Settings
CAS_SERVER_URL = "https://cas-test.clsi.ca/"
CAS_SERVICE_DESCRIPTION = "LIVE"
CAS_LOGOUT_COMPLETELY = True
CAS_CREATE_USER = True
CAS_REDIRECT_URL = 'login'
CAS_LOGIN_URL_NAME = 'login'
CAS_LOGOUT_URL_NAME = 'logout'