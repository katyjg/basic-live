import json

from collections import defaultdict
from datetime import datetime

from django import template
from django.utils.safestring import mark_safe

from basiclive.core.lims.models import *
from .converter import humanize_duration
from ..stats import SHIFT, get_data_periods

register = template.Library()

COLOR_SCHEME = ["#883a6a", "#1f77b4", "#aec7e8", "#5cb85c", "#f0ad4e"]
GRAY_SCALE = ["#000000", "#555555", "#888888", "#cccccc", "#eeeeee"]


@register.simple_tag(takes_context=False)
def get_data_stats(bl, year):
    data = bl.datasets.all()
    years = get_data_periods()
    kinds = list(DataType.objects.annotate(count=Count('datasets', filter=Q(datasets__beamline=bl))).filter(count__gt=0))
    yearly_info = defaultdict(lambda: defaultdict(int))

    for summary in data.values('created__year', 'kind__name').annotate(count=Count('pk')):
        yearly_info[summary['created__year']][summary['kind__name']] = summary['count']
    yearly = []
    for k in kinds:
        kind_counts = [yearly_info[yr][k.name] for yr in years]
        yearly.append([k.name] + kind_counts + [sum(kind_counts)])
    year_counts = [sum(yearly_info[yr].values()) for yr in years]
    yearly.append(['Total'] + year_counts + [sum(year_counts)])
    histogram_data = []

    for year, counts in sorted(yearly_info.items()):
        series = {'Year': year}
        series.update(counts)
        histogram_data.append(series)

    beam_size_query = data.filter(beam_size__isnull=False)
    beam_sizes = beam_size_query.values('beam_size').annotate(count=Count('pk'))
    beam_sizes_totals = beam_size_query.count()

    data = data.filter(created__year=year)
    stats = {'details': [
        {
            'title': '{} Beamline Parameters'.format(year),
            'description': 'Data Collection Parameters Summary',
            'style': 'row',
            'content': [
                {
                    'title': 'Attenuation vs. Exposure Time',
                    'kind': 'scatterplot',
                    'data': {
                        'x': ['Exposure'] + list(data.values_list('exposure_time', flat=True)),
                        'y1': [['Attenuation'] + list(data.values_list('attenuation', flat=True))],
                    },
                    'style': 'col-12 col-sm-6'
                },
                {
                    'title': 'Beam Size',
                    'kind': 'pie',
                    'data': [
                        {
                            'label': "{:0.0f}".format(entry['beam_size']),
                            'value': 360 * entry['count'] / beam_sizes_totals,
                        }
                        for entry in beam_sizes
                    ],
                    'style': 'col-12 col-sm-6'
                } if beam_sizes_totals else {},
            ]
        },
        {
            'title': '',
            'style': 'row',
            'content': [
                {
                    'title': e.title(),
                    'kind': 'histogram',
                    'data': {
                        'data': [float(d) for d in data.values_list(e, flat=True) if d != None],
                    },
                    'style': 'col-12 col-sm-6'
                } for i, e in enumerate(['energy', 'exposure_time', 'attenuation'])] if data.count() else []
        }
    ]}
    return mark_safe(json.dumps(stats))


@register.simple_tag(takes_context=False)
def get_yearly_sessions(user):
    yr = timezone.localtime() - timedelta(days=365)
    return user.sessions.filter(
        pk__in=Stretch.objects.filter(end__gte=yr).values_list('session__pk', flat=True).distinct())


@register.simple_tag(takes_context=False)
def samples_per_hour(user, sessions):
    ttime = total_time(sessions, user)
    samples = sum([s.samples().count() for s in sessions])
    return round(samples / ttime, 2) if ttime else 'None'


@register.filter
def samples_per_hour_all(category):
    yr = timezone.localtime() - timedelta(days=365)
    sessions = Session.objects.filter(
        pk__in=Stretch.objects.filter(end__gte=yr).values_list('session__pk', flat=True).distinct())
    ttime = sum(
        [s.total_time() for s in sessions.filter(project__pk__in=category.projects.values_list('pk', flat=True))])
    samples = sum(
        [s.samples().count() for s in sessions.filter(project__pk__in=category.projects.values_list('pk', flat=True))])
    return round(samples / ttime, 2) if ttime else 'None'


@register.filter
def samples_per_hour_percentile(category, user):
    yr = timezone.localtime() - timedelta(days=365)
    sessions = Session.objects.filter(
        pk__in=Stretch.objects.filter(end__gte=yr).values_list('session__pk', flat=True).distinct())
    data = {project.username: {'samples': sum([s.samples().count() for s in sessions.filter(project=project)]),
                               'total_time': sum([s.total_time() for s in sessions.filter(project=project)])}
            for project in category.projects.all()}
    averages = sorted([round(v['samples'] / v['total_time'], 2) if v['total_time'] else 0 for v in data.values()])
    my_avg = round(data[user.username]['samples'] / data[user.username]['total_time'], 2) \
        if data[user.username]['total_time'] else 0

    return round((averages.index(my_avg) + 0.5 * averages.count(my_avg)) * 100 / len(averages))


@register.simple_tag(takes_context=False)
def get_project_stats(user):
    data = user.datasets.all()
    stats = {}
    years = get_data_periods()

    kinds = [k for k in DataType.objects.all() if data.filter(kind=k).exists()]
    yrs = [{'Year': yr} for yr in years]
    for yr in yrs:
        yr.update({k.name: data.filter(created__year=yr['Year'], kind=k).count() for k in kinds})
    yearly = [
        [k.name] + [data.filter(created__year=yr, kind=k).count() for yr in years] + [data.filter(kind=k).count()]
        for k in kinds]
    totals = [['Total'] + [data.filter(created__year=yr).count() for yr in years] + [data.count()]]

    shifts = total_shifts(user.sessions.all(), user)
    ttime = total_time(user.sessions.all(), user)
    shutters = round(sum([d.num_frames * d.exposure_time for d in data if d.exposure_time]), 2)/3600.

    stats = {'details': [
        {
            'title': '{} Summary'.format(user.username.title()),
            'description': 'Data Collection Summary for {}'.format(user.username.title()),
            'style': "col-12",
            'content': [
                {
                    'title': 'Time Usage',
                    'kind': 'table',
                    'data': [
                        ['Shifts Used', '{} ({})'.format(shifts, humanize_duration(shifts * SHIFT))],
                        ['Actual Time', '{} % ({})'.format(round(ttime / (shifts * SHIFT), 2), humanize_duration(ttime))],
                        ['Shutters Open', '{}'.format(humanize_duration(shutters))],
                    ],
                    'header': 'column',
                    'style': 'col-sm-6'
                },
                {
                    'title': 'Overall Statistics',
                    'kind': 'table',
                    'data': [
                        ['Sessions', user.sessions.count()],
                        ['Shipments / Containers', "{} / {}".format(
                            user.shipments.count(),
                            user.containers.filter(status__gte=Container.STATES.ON_SITE).count())],
                        ['Groups / Samples', "{} / {}".format(
                            user.groups.filter(shipment__status__gte=Shipment.STATES.ON_SITE).count(),
                            user.samples.filter(container__status__gte=Container.STATES.ON_SITE).count())],
                    ],
                    'header': 'column',
                    'style': 'col-sm-6'
                },
                {
                    'title': '',
                    'kind': 'table',
                    'data': [[''] + years + ['All']] + yearly + totals,
                    'header': 'row',
                    'style': 'col-sm-8'
                },
                {
                    'title': '',
                    'kind': 'histogram',
                    'data': {
                        'x-label': 'Year',
                        'data': yrs,
                    },
                    'style': 'col-sm-4'
                }
            ]
        }
        ]}
    return stats


def js_epoch(dt):
    return int("{:0.0f}000".format(dt.timestamp() if dt else datetime.now().timestamp()))


@register.filter
def get_years(bl):
    return sorted(
        {v['created'].year for v in Data.objects.filter(beamline=bl).values("created").order_by("created").distinct()})


@register.filter
def started(data):
    return data.modified - timedelta(seconds=(data.exposure_time * data.num_frames))


def total_shifts(sessions, project):
    shifts = [y for x in [s.shifts() for s in sessions.filter(project=project)] for y in x]
    return len(set(shifts))


def total_time(sessions, project):
    return sum([s.total_time() for s in sessions.filter(project=project)])
