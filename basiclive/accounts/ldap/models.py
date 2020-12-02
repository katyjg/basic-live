from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from . import slap

User = get_user_model()


@receiver(post_save, sender=User)
def on_project_create(sender, instance, created, **kwargs):
    if created:
        user_info = {
            'username': instance.username,
            'password': '',
            'first_name': instance.first_name,
            'last_name': instance.last_name
        }
        ldap = slap.Directory()
        info = ldap.add_user(user_info)
        instance.name = info.get('username')
        instance.save()


@receiver(pre_delete, sender=User)
def on_project_delete(sender, instance, **kwargs):
    directory = slap.Directory()
    directory.delete_user(instance.name)

