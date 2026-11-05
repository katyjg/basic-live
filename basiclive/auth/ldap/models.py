from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from basiclive.auth.ldap.conf import settings
from . import slap


def is_directory_management_enabled():
    """
    Check if LDAP directory management is enabled.
    Opt-in via settings.MANAGE_DIRECTORY = True or having settings.MANAGER_DN configured.
    """
    return bool(settings.MANAGE_DIRECTORY or settings.MANAGER_DN)


@receiver(post_save)
def on_user_create(sender, instance, created, **kwargs):
    User = get_user_model()
    if sender != User or not created:
        return
    if not is_directory_management_enabled():
        return

    username = getattr(instance, 'username', getattr(instance, 'name', ''))
    user_info = {
        'username': username,
        'password': '',
        'first_name': getattr(instance, 'first_name', ''),
        'last_name': getattr(instance, 'last_name', '')
    }
    ldap = slap.Directory()
    info = ldap.add_user(user_info)
    ldap_username = info.get('username') if info else None
    if ldap_username:
        if hasattr(instance, 'username') and instance.username != ldap_username:
            instance.username = ldap_username
            instance.save(update_fields=['username'])
        elif hasattr(instance, 'name') and instance.name != ldap_username:
            instance.name = ldap_username
            instance.save(update_fields=['name'])


@receiver(pre_delete)
def on_user_delete(sender, instance, **kwargs):
    User = get_user_model()
    if sender != User:
        return
    if not is_directory_management_enabled():
        return

    name = getattr(instance, 'username', getattr(instance, 'name', ''))
    directory = slap.Directory()
    directory.delete_user(name)
