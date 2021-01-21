from django.template import Library
from django.db.models import Q
from .. import models
register = Library()


@register.filter
def num_session_samples(group, session):
    return group.samples.filter(pk__in=session.datasets.values_list('sample__pk')).count()


@register.simple_tag
def group_samples(group, session=None):
    if session and group:
        return group.samples.filter(datasets__session=session.pk).distinct()
    elif session:
        return models.Sample.objects.filter(datasets__session=session.pk, group__isnull=True).distinct()
    elif group:
        return group.samples.all()
    else:
        return  models.Sample.objects.none()


@register.filter
def request_samples(request, group):
    return group.samples.filter(pk__in=[s.pk for s in request.sample_list()])


@register.filter
def group_parameters(group):
    parameters = [
        None if not group.resolution else '{:0.1f} Å'.format(group.resolution),
        None if not group.energy else '{:0.3f} keV'.format(group.energy),
        None if not group.absorption_edge else group.absorption_edge,
    ]
    return ", ".join(filter(None, parameters))


@register.simple_tag
def sample_data(sample, session=None):
    if session:
        return {
            'data': sample.datasets.filter(session=session),
            'reports': sample.reports().filter(Q(data__in=sample.datasets.filter(session=session)) | Q(data__isnull=True))
        }
    return {
        'data': sample.datasets.all(),
        'reports': sample.reports().all()
    }

