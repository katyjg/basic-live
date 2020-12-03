from django.db import models
from django.utils.translation import ugettext as _
from model_utils import Choices
from model_utils.models import TimeStampedModel

from basiclive.core.lims.models import Project, Session, Beamline


class LikertScale(models.Model):
    statement = models.CharField(max_length=250, null=True)
    worst = models.CharField("-2", max_length=25)
    worse = models.CharField("-1", max_length=25)
    better = models.CharField("1", max_length=25)
    best = models.CharField("2", max_length=25)

    class Meta:
        verbose_name = "Likert Scale"

    def __str__(self):
        return ' | '.join([self.worst, self.worse, self.better, self.best])

    def choices(self):
        return Choices(
            (-2, 'WORST', self.worst),
            (-1, 'WORSE', self.worse),
            (1, 'BETTER', self.better),
            (2, 'BEST', self.best),
            (0, 'NOT_APPLICABLE', _('N/A')),
        )


class SupportArea(models.Model):
    name = models.CharField(max_length=200)
    user_feedback = models.BooleanField(_('Add to User Experience Survey'), default=False)
    external = models.BooleanField(_("External (out of the beamline's control)"), default=False)
    scale = models.ForeignKey(LikertScale, on_delete=models.SET_NULL, null=True, blank=True, related_name='areas')

    def __str__(self):
        return self.name


class Feedback(TimeStampedModel):
    session = models.ForeignKey(Session, blank=True, null=True, on_delete=models.SET_NULL, related_name='feedback')
    comments = models.TextField(blank=True, null=True)
    contact = models.BooleanField(_('Contact User'), default=False)

    def __str__(self):
        return self.session and self.session.name or "No Session"


class AreaFeedback(models.Model):
    feedback = models.ForeignKey(Feedback, on_delete=models.CASCADE, related_name='areas')
    area = models.ForeignKey(SupportArea, on_delete=models.CASCADE, related_name='impressions')
    rating = models.IntegerField(default=0)

    def get_rating_display(self):
        return self.area.scale.choices()[self.rating]


class SupportRecord(TimeStampedModel):
    TYPE = Choices(
        ('problem', _('Problem')),
        ('info', _('Info')),
    )
    kind = models.CharField(_("Kind"), max_length=20, default=TYPE.info, choices=TYPE)
    areas = models.ManyToManyField(SupportArea, blank=True, related_name='help')
    staff = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, related_name='help')
    beamline = models.ForeignKey(Beamline, on_delete=models.SET_NULL, null=True, related_name='help')
    comments = models.TextField(blank=True, null=True)
    lost_time = models.FloatField(_('Time Lost (hours)'), default=0.0)
    staff_comments = models.TextField(blank=True, null=True)

    def __str__(self):
        return "{} | {} | {}".format(self.staff, self.beamline, self.project)

    @property
    def area_names(self):
        return ' | '.join(self.areas.values_list("name", flat=True))
