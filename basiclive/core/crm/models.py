from django.conf import settings
from django.db import models, transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext as _
from model_utils import Choices
from model_utils.models import TimeStampedModel

from basiclive.core.lims.models import Project, Session, Beamline


class LikertScale(models.Model):
    statement = models.CharField(max_length=250, null=True)
    worst = models.CharField("-2", max_length=25)
    worse = models.CharField("-1", max_length=25)
    neutral = models.CharField("0", max_length=25, default="Neutral")
    better = models.CharField("1", max_length=25)
    best = models.CharField("2", max_length=25)

    class Meta:
        verbose_name = _("Likert Scale")
        verbose_name_plural = _("Likert Scales")

    def __str__(self):
        return ' | '.join([self.worst, self.worse, self.neutral, self.better, self.best])

    def get_label(self, rating):
        return self.choices()[rating]

    def choices(self):
        return Choices(
            (-2, 'WORST', self.worst),
            (-1, 'WORSE', self.worse),
            (0, 'NEUTRAL', self.neutral),
            (1, 'BETTER', self.better),
            (2, 'BEST', self.best),
        )


class SupportArea(models.Model):
    name = models.CharField(_("Short Name"), max_length=200)
    label = models.CharField(_("Label"), max_length=500, blank=True, default="")
    user_feedback = models.BooleanField(_('Add to User Experience Survey'), default=False)
    external = models.BooleanField(_("External (out of the beamline's control)"), default=False)
    scale = models.ForeignKey(LikertScale, on_delete=models.SET_NULL, null=True, blank=True, related_name='areas')

    class Meta:
        verbose_name = _("Support Area")
        verbose_name_plural = _("Support Areas")

    def __str__(self):
        return self.name

    @property
    def display_label(self):
        return self.label or self.name


class Feedback(TimeStampedModel):
    session = models.ForeignKey(Session, blank=True, null=True, on_delete=models.SET_NULL, related_name='feedback')
    comments = models.TextField(blank=True, null=True)
    contact = models.BooleanField(_('Contact User'), default=False)

    class Meta:
        verbose_name = _("Feedback")
        verbose_name_plural = _("Feedbacks")

    def __str__(self):
        return f"Feedback #{self.pk} for {self.session}"


class AreaFeedback(models.Model):
    feedback = models.ForeignKey(Feedback, on_delete=models.CASCADE, related_name='areas')
    area = models.ForeignKey(SupportArea, on_delete=models.CASCADE, related_name='impressions')
    label = models.CharField(max_length=200, blank=True, null=True)   # e.g 'Excellent', 'Good', 'Poor', etc.
    rating = models.IntegerField(default=0)  # Rating based on the scale (-2, -1, 0, 1, 2)

    class Meta:
        verbose_name = _("Area Feedback")
        verbose_name_plural = _("Area Feedbacks")
        indexes = [
            models.Index(fields=['feedback', 'area']),
        ]

    def get_rating_display(self):
        return self.area.scale.get_label(self.rating)

    def __str__(self):
        return f"{self.area.name}: {self.get_rating_display()}"


class SupportRecord(TimeStampedModel):
    TYPE = Choices(
        ('problem', _('Problem')),
        ('info', _('Info')),
    )
    kind = models.CharField(_("Kind"), max_length=20, default=TYPE.info, choices=TYPE)
    area = models.ForeignKey(SupportArea, on_delete=models.SET_NULL, null=True, blank=True, related_name='records')
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='support_records'
    )
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, related_name='help')
    beamline = models.ForeignKey(Beamline, on_delete=models.SET_NULL, null=True, related_name='help')
    comments = models.TextField(blank=True, null=True)
    lost_time = models.FloatField(_('Time Lost (hours)'), default=0.0)
    staff_comments = models.TextField(blank=True, null=True)
    previous = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='next_records',
        verbose_name=_('Previous Record'),
    )

    class Meta:
        verbose_name = _("Support Record")
        verbose_name_plural = _("Support Records")

    def __str__(self):
        return f"{self.staff} | {self.beamline} | {self.project}"

    @property
    def area_names(self):
        return self.area.name if self.area else ""

    @property
    def next(self):
        return self.next_records.first()

    def _get_predecessor(self):
        qs = SupportRecord.objects.filter(
            area_id=self.area_id,
            kind=self.kind,
            beamline_id=self.beamline_id,
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if self.created:
            if self.pk:
                qs = qs.filter(models.Q(created__lt=self.created) | models.Q(created=self.created, pk__lt=self.pk))
            else:
                qs = qs.filter(created__lte=self.created)
        return qs.order_by('-created', '-pk').first()

    def _get_successor(self):
        qs = SupportRecord.objects.filter(
            area_id=self.area_id,
            kind=self.kind,
            beamline_id=self.beamline_id,
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if self.created:
            if self.pk:
                qs = qs.filter(models.Q(created__gt=self.created) | models.Q(created=self.created, pk__gt=self.pk))
            else:
                qs = qs.filter(created__gt=self.created)
        return qs.order_by('created', 'pk').first()

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.created:
            self.created = timezone.now()

        orig = None
        if self.pk:
            orig = SupportRecord.objects.filter(pk=self.pk).values(
                'id', 'area_id', 'kind', 'beamline_id', 'created', 'previous_id'
            ).first()

        if orig:
            partition_or_time_changed = (
                orig['area_id'] != self.area_id
                or orig['kind'] != self.kind
                or orig['beamline_id'] != self.beamline_id
                or orig['created'] != self.created
            )
            if partition_or_time_changed:
                SupportRecord.objects.filter(previous_id=self.pk).exclude(pk=self.pk).update(
                    previous_id=orig['previous_id']
                )

        pred = self._get_predecessor()
        self.previous = pred

        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)
            update_fields.add('previous')
            kwargs['update_fields'] = update_fields

        super().save(*args, **kwargs)

        successor = self._get_successor()
        if successor:
            SupportRecord.objects.filter(pk=successor.pk).update(previous_id=self.pk)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        SupportRecord.objects.filter(previous_id=self.pk).update(previous_id=self.previous_id)
        return super().delete(*args, **kwargs)


@receiver(pre_delete, sender=SupportRecord)
def support_record_pre_delete(sender, instance, **kwargs):
    SupportRecord.objects.filter(previous_id=instance.pk).update(previous_id=instance.previous_id)


