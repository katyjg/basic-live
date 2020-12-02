
from django.db import models
from django.utils import timezone
from django.db.models import Q, F, Value, IntegerField, TextField, Subquery, OuterRef
from django.conf import settings
from memoize import memoize
from . import signals


class TMQuerySet(models.QuerySet):

    def expire(self):
        now = timezone.now()
        q = super().filter(expired__gt=now)
        result = q.update(expired=now)
        for obj in q:
            signals.expired.send(obj.__class__, obj)
        return result

    def inactive(self):
        return super().filter(expired__lte=timezone.now())

    def active(self):
        return self.filter(expired__gt=timezone.now())

    def as_of(self, dt):
        return self.filter(created__lte=dt, expired__gt=dt)


class TMObjectsManager(models.Manager.from_queryset(TMQuerySet)):
    pass


class TMEntriesManager(TMObjectsManager):

    def get_queryset(self):
        return super().get_queryset().active()


class TimedModel(models.Model):
    """
    A model that manages objects that can expire, use the entries manager to work only with active
    objects, that is, those with an expiry date in the future.
    """

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    expired = models.DateTimeField(default=timezone.datetime(9999, 12, 31, tzinfo=timezone.utc), db_index=True, editable=False)

    objects = TMObjectsManager()
    entries = TMEntriesManager()

    class Meta:
        abstract = True

    def expire(self, *args, **kwargs):
        self.expired = timezone.now()
        super().save()
        signals.expired.send(sender=self.__class__, instance=self)

    def is_active(self):
        return self.expired >= timezone.now()


class TPQuerySet(models.QuerySet):

    def as_of(self, dt):
        q = super().filter(effective__lte=dt, owner=OuterRef('owner')).order_by('-effective')
        return super().filter(pk=Subquery(q.values('pk')[:1]))

    def active(self):
        now = timezone.now()
        q = super().filter(owner=OuterRef('owner'), effective__lte=now).order_by('-effective')
        return super().filter(pk=Subquery(q.values('pk')[:1]))

    def inactive(self):
        now = timezone.now()
        q = super().filter(owner=OuterRef('owner'), effective__lte=now).order_by('-effective')
        return super().exclude(pk=Subquery(q.values('pk')[:1]))


class TPObjectsManager(models.Manager.from_queryset(TPQuerySet)):
    pass


class TPEntriesManager(TPObjectsManager):

    def get_queryset(self):
        return super().get_queryset().active()


class TemporalProfile(TimedModel):
    """
    A TemporalProfile:
    A Timed modal with addition capability of providing an effective date. Objects can have
    effective dates in the future. Use the entries manager to work with active objects.  Active
    objects are those which have the latest effective dates for a given owner

    Subclasses
    should override the owner field to point to the Model for which a temporal profile is desired.

    Use the 'modify()' method instead of 'save()' to expire the current profile, and create a new
    effective profile.
    """
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    effective = models.DateTimeField()

    objects = TPObjectsManager()
    entries = TPEntriesManager()

    class Meta:
        abstract = True
        unique_together = (('owner', 'effective'), )
        indexes = [
            models.Index(fields=['owner', 'effective'])
        ]

    def modify(self, **kwargs):
        now = timezone.now()
        for k,v in kwargs.items():
            setattr(self, k, v)
        if not 'effective' in kwargs:
            self.effective = now
        self.pk = None
        super().save()

    def is_active(self):
        return TemporalProfile.entries.filter(owner_id=self.owner_id, pk__ne=self.pk).exists()

    def __str__(self):
        return '{} > {}'.format(self.owner, self.effective)


class TMPQuerySet(TMQuerySet):

    def as_of(self, date):
        q = super().as_of(date).filter(effective__lte=date).order_by('-effective')
        return super().as_of(date).filter(pk=Subquery(q.values('pk')[:1]))

    def active(self):
        now = timezone.now()
        q = super().filter(effective__lte=now, expired__gt=now).order_by('-effective')
        return super().filter(pk=Subquery(q.values('pk')[:1]))

    def inactive(self):
        now = timezone.now()
        q = super().filter(effective__lte=now, expired__gt=now).order_by('-effective')
        return super().exclude(pk=Subquery(q.values('pk')[:1]))


class TMPObjectsManager(models.Manager.from_queryset(TMPQuerySet)):
    pass


class TMPEntriesManager(TMPObjectsManager):

    def get_queryset(self):
        return super().get_queryset().active()


class TemporalModel(TimedModel):
    effective = models.DateTimeField()

    objects = TMPObjectsManager()
    entries = TMPEntriesManager()

    class Meta:
        abstract = True

    def modify(self, **kwargs):
        now = timezone.now()
        for k,v in kwargs.items():
            setattr(self, k, v)
        if not 'effective' in kwargs:
            self.effective = now
        self.pk = None
        super().save()

    def is_active(self):
        return TemporalModel.objects.active().filter(pk=self.pk).exists()


def unique_for_time(*args):
    return args + ('expired', )


def unique_for_profile(*args):
    return args + ('effective',)

def unique_for_temporal(*args):
    return unique_for_time(*args) + ('effective',)