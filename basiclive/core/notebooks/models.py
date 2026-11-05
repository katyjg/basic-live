import mimetypes
import os
import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils import Choices

from .utils import timeish


class Notebook(models.Model):
    ACCESS = Choices(
        (0, 'private', _('Private')),
        (1, 'internal', _('Internal')),
        (2, 'public', _('Public')),
    )
    EDITOR = Choices(
        (0, 'owner', _('Owner')),
        (1, 'team', _('Members')),
        (2, 'users', _('All')),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created = models.DateTimeField(_('created'), auto_now_add=True)
    modified = models.DateTimeField(_('modified'), auto_now=True)
    name = models.SlugField(_('name'), max_length=100, db_index=True)
    title = models.CharField(_('title'), max_length=256)
    description = models.TextField(_('description'), blank=True)

    class Meta:
        verbose_name = _("Notebook")
        verbose_name_plural = _("Notebooks")

    def __str__(self):
        return self.title or self.name

    def can_edit(self, user):
        return user.is_superuser or user.is_staff

    def can_view(self, user):
        return user.is_superuser or user.is_staff


class EntryTypeManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class EntryType(models.Model):
    name = models.SlugField(_('name'), max_length=20, unique=True)

    objects = EntryTypeManager()

    class Meta:
        verbose_name = _("Entry Type")
        verbose_name_plural = _("Entry Types")

    def natural_key(self):
        return (self.name,)

    def icon(self):
        # Return the icon associated with this entry type
        return f"{self.name.lower()}-entry"

    def __str__(self):
        return self.name


def entry_storage(instance, filename):
    """
    Generate a path name for storing an entry file
    :param instance: Entry instance
    :param filename: filename of file being stored
    :return: relative storage path
    """
    extension = os.path.splitext(filename)[1]
    new_filename = f'{instance.kind.name}-{instance.pk or uuid.uuid4().hex[:8]}{extension.lower()}'
    entry_date = timezone.localdate(instance.created) if instance.created else timezone.localdate()
    return os.path.join(
        'notebooks',
        str(instance.notebook.pk),
        entry_date.isoformat(),
        new_filename
    )


class Entry(models.Model):
    created = models.DateTimeField(_('created'), default=timezone.now, db_index=True)
    modified = models.DateTimeField(_('modified'), auto_now=True)
    notebook = models.ForeignKey(Notebook, related_name='entries', on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='entries', null=True)
    tags = models.JSONField(_('Tags'), default=list)
    kind = models.ForeignKey(EntryType, on_delete=models.CASCADE)
    text = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to=entry_storage, blank=True, null=True)

    class Meta:
        verbose_name = _("Entry")
        verbose_name_plural = _("Entries")
        ordering = ['created']

    def __str__(self):
        return f'{self.notebook.name}-{self.created.isoformat()}'

    def is_editable(self):
        return timezone.localdate(self.created) == timezone.localdate(timezone.now()) and not self.annotations.exists()

    def can_edit(self, user):
        if not user or not user.is_authenticated:
            return False
        return self.is_editable() and (user == self.author or user.is_superuser)

    def can_view(self, user):
        return self.notebook.can_view(user)

    def mimetype(self):
        if not self.file:
            return None
        mime, _ = mimetypes.guess_type(self.file.name)
        return mime

    def tag_string(self):
        return ','.join(self.tags)


# This receiver handles the file deletion after the entry instance is deleted
@receiver(post_delete, sender=Entry)
def delete_file_on_model_delete(sender, instance, **kwargs):
    if instance.file:
        # save=False prevents Django from attempting to re-save the object to the database
        instance.file.delete(save=False)


class AnnotationQueryset(models.QuerySet):
    def with_quotes(self):
        return self.exclude(quote='')


class AnnotationManager(models.Manager.from_queryset(AnnotationQueryset)):
    use_for_related_fields = True


class Annotation(models.Model):
    created = models.DateTimeField(_('created'), default=timezone.now)
    entry = models.ForeignKey(Entry, related_name='annotations', on_delete=models.CASCADE)
    quote = models.TextField(_('Quote'), blank=True, default='')
    text = models.TextField(_('Comment text'))
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='annotations', null=True)

    objects = AnnotationManager()

    class Meta:
        verbose_name = _("Annotation")
        verbose_name_plural = _("Annotations")

    def __str__(self):
        return f'Annotation by @{self.author.name} on {self.entry}'

    def json(self):
        return {
            'id': self.pk,
            'entry_id': self.entry_id,
            'author': f'@{self.author.name}',
            'time': timeish(timezone.localtime(self.created)),
            'text': self.text,
            'quote': self.quote,
        }
