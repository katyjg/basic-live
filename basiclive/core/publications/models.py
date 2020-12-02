from django.db import models
from django.utils.translation import ugettext as _
from model_utils.models import TimeStampedModel
from model_utils import Choices
from basiclive.utils import fields
from basiclive.utils import temporal


class SubjectArea(TimeStampedModel):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    code = models.CharField(_('ASJC Code'), max_length=10)
    parent = models.ForeignKey("SubjectArea", blank=True, null=True, related_name="children", on_delete=models.SET_NULL)

    def __str__(self):
        return self.name


class TagManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class Tag(TimeStampedModel):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    objects = TagManager()

    def __str__(self):
        return self.name

    def natural_key(self):
        return self.name,


class Journal(TimeStampedModel):
    title = models.TextField()
    short_name = models.TextField(blank=True, null=True)
    codes = fields.StringListField("ISSN", unique=True)
    publisher = models.TextField(blank=True, null=True)
    topics = models.ManyToManyField(SubjectArea, related_name='journals', blank=True)
    metrics = models.ForeignKey('JournalProfile', null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.title


class JournalProfile(temporal.TemporalProfile):
    owner = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='profiles')
    sjr_rank = models.FloatField("SJR-Rank", default=0.0, null=True)
    sjr_quartile = models.SmallIntegerField("SJR-Quartile", default=4, null=True)
    impact_factor = models.FloatField("Impact Factor", default=0.0, null=True)
    h_index = models.IntegerField("H-Index", default=1.0, null=True)

    def __str__(self):
        return "{} > {}".format(self.owner, self.effective.isoformat())


class Funder(TimeStampedModel):
    name = models.TextField(unique=True)
    code = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return self.name


class Publication(TimeStampedModel):
    TYPES = Choices(
        ('article', _('Peer-Reviewed Article')),
        ('proceeding', _('Conference Proceeding')),
        ('phd_thesis', _('Doctoral Thesis')),
        ('msc_thesis', _('Masters Thesis')),
        ('magazine', _('Magazine Article')),
        ('book', _('Book')),
        ('chapter', _('Book / Chapter')),
        ('patent', _('Patent')))

    published = models.DateField(_('Published'))
    authors = models.TextField()
    #projects = models.ManyToManyField(Project, related_name="publications", blank=True)
    code = models.CharField(max_length=255, null=True, unique=True)
    keywords = fields.StringListField(blank=True)
    abstract = models.TextField(null=True, blank=True)
    kind = models.CharField(_('Type'), choices=TYPES, default=TYPES.article, max_length=20)
    active = models.BooleanField(default=False)
    comments = models.TextField(blank=True, null=True)
    funders = models.ManyToManyField(Funder, related_name="publications", blank=True)
    tags = models.ManyToManyField(Tag, related_name='publications', verbose_name='Tags', blank=True)
    topics = models.ManyToManyField(SubjectArea, related_name="publications", verbose_name="Subject Areas", blank=True)
    main_title = models.TextField(blank=True, null=True)
    title = models.TextField()
    editor = models.TextField(blank=True, null=True)
    publisher = models.CharField(max_length=100, blank=True, null=True)
    journal = models.ForeignKey(Journal, related_name='articles', on_delete=models.CASCADE, null=True)
    volume = models.CharField(max_length=100, blank=True, null=True)
    issue = models.CharField(max_length=20, blank=True, null=True)
    pages = models.CharField(max_length=20, blank=True, null=True)
    metrics = models.ForeignKey("Metric", null=True, on_delete=models.SET_NULL, related_name='publication')

    def __str__(self):
        return self.code

    def cite(self):
        return f"{self.authors} ({self.published.year}) {self.title}. {self.journal and self.journal.short_name or ''}. {self.code}"


class Metric(temporal.TemporalProfile):
    owner = models.ForeignKey(Publication, null=True, on_delete=models.CASCADE, related_name='all_metrics')
    citations = models.IntegerField(default=0)
    mentions = models.IntegerField(default=0)

    def __str__(self):
        return '{}'.format(self.citations)


class Deposition(TimeStampedModel):
    code = models.CharField(max_length=20, unique=True)
    title = models.TextField()
    authors = models.TextField()
    #projects = models.ManyToManyField(Project, related_name="publications", blank=True)
    doi = models.CharField(max_length=255, unique=True)
    resolution = models.FloatField(default=0.0)
    released = models.DateField()
    deposited = models.DateField()
    collected = models.DateField(null=True)
    tags = models.ManyToManyField(Tag, related_name='depositions', verbose_name='Tags')
    reference = models.ForeignKey(Publication, related_name='depositions', null=True, on_delete=models.SET_NULL)
    citation = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.code