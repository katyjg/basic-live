from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from django_cas_ng.signals import cas_user_authenticated

import logging
logger = logging.getLogger(__name__)

User = get_user_model()


@receiver(cas_user_authenticated)
def update_user(sender, **kwargs):
    user = User.objects.get(username=kwargs.get('username'))
    if kwargs.get('created'):
        logger.info("New account {} created".format(user.username))
