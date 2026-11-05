from django.core.exceptions import PermissionDenied
from django.db import models


class SingletonManager(models.Manager):
    """
    Overrides standard creation methods to force compliance with the singleton pattern.
    """

    def create(self, **kwargs):
        """
        Forces creation fields into the singular ID=1 record.
        """
        # Clean out any incoming ID parameters to guarantee we use id=1
        kwargs.pop('id', None)
        kwargs.pop('pk', None)

        # update_or_create ensures the record updates if it exists, or creates it if it doesn't
        instance, _ = self.update_or_create(id=1, defaults=kwargs)
        return instance

    def get_or_create(self, defaults=None, **kwargs):
        """
        Always fetches or creates the entry at ID=1, ignoring filter arguments.
        """
        # Singletons cannot have unique lookups other than id=1.
        # We redirect the initialization default dict to match the payload.
        lookup_defaults = dict(defaults or {})
        if kwargs:
            kwargs.pop('id', None)
            kwargs.pop('pk', None)
            lookup_defaults.update(kwargs)

        return super().get_or_create(id=1, defaults=lookup_defaults)

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        """
        Forces any update/create lookup mapping to target ID=1.
        """
        lookup_defaults = dict(defaults or {})
        if kwargs:
            # Strip out lookups from kwargs to safely merge into defaults
            kwargs.pop('id', None)
            kwargs.pop('pk', None)
            lookup_defaults.update(kwargs)

        return super().update_or_create(id=1, defaults=lookup_defaults, create_defaults=create_defaults)

    def bulk_create(self, objs, *args, **kwargs):
        raise PermissionDenied("Bulk creation is prohibited on Singleton models.")

    def bulk_update(self, objs, fields, *args, **kwargs):
        raise PermissionDenied("Bulk updating is prohibited on Singleton models.")


class Singleton(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = SingletonManager()

    class Meta:
        abstract = True

    @classmethod
    def load(cls):
        # Always fetch or create the row with id=1
        obj, created = cls.objects.get_or_create()
        return obj

    def save(self, *args, **kwargs):
        self.clean()
        self.id = 1
        # Ensure that only this entry exists by deleting all other rows
        self.__class__.objects.exclude(id=self.id).delete()
        super().save(*args, **kwargs)
