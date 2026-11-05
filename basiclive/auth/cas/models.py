import logging
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

try:
    from django_cas_ng.signals import cas_user_authenticated
except ImportError:
    cas_user_authenticated = None


def update_user(sender, **kwargs):
    User = get_user_model()
    try:
        user = User.objects.get(username=kwargs.get('username'))
    except User.DoesNotExist:
        return
    if kwargs.get('created'):
        logger.info("New user {} authenticated via CAS".format(user.username))


if cas_user_authenticated is not None:
    cas_user_authenticated.connect(update_user)
