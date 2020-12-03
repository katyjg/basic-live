import calendar
from collections import defaultdict
from datetime import datetime, timedelta
from math import ceil

import numpy
from django.conf import settings
from django.db.models import Count, Sum, F, Avg, FloatField, Case, When, IntegerField, Q, DateTimeField, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.template.defaultfilters import linebreaksbr
from django.utils import timezone
from django.utils.timesince import timesince
from memoize import memoize

from basiclive.core.lims.models import Data, Sample, Session, Project, AnalysisReport, Container, Shipment, ProjectType, DataType
from basiclive.utils.functions import ShiftEnd, ShiftStart, ShiftIndex
from basiclive.utils.misc import humanize_duration, natural_duration

HOUR_SECONDS = 3600
SHIFT = getattr(settings, "HOURS_PER_SHIFT", 8)
SHIFT_SECONDS = SHIFT * HOUR_SECONDS
MAX_COLUMN_USERS = 30


class ColorScheme(object):
    Live4 = ["#8f9f9a", "#c56052", "#9f6dbf", "#a0b552"]
    Live8 = ["#073B4C", "#06D6A0", "#FFD166", "#EF476F", "#118AB2", "#7F7EFF", "#afc765", "#78C5E7"]
    Live16 = [
        "#67aec1", "#c45a81", "#cdc339", "#ae8e6b", "#6dc758", "#a084b6", "#667ccd", "#cd4f55",
        "#805cd6", "#cf622d", "#a69e4c", "#9b9795", "#6db586", "#c255b6", "#073B4C", "#FFD166",
    ]


def js_epoch(dt):
    return int("{:0.0f}000".format(dt.timestamp() if dt else datetime.now().timestamp()))


@memoize(timeout=HOUR_SECONDS)
def get_data_periods(period='year'):
    field = 'created__{}'.format(period)
    return sorted(Data.objects.values_list(field, flat=True).order_by(field).distinct())


def make_table(data, columns, rows, total_col=True, total_row=True):
    ''' Converts a list of dictionaries into a list of lists ready for displaying as a table
        data: list of dictionaries (one dictionary per column header)
        columns: list of column headers to display in table, ordered the same as data
        rows: list of row headers to display in table
    '''
    header_row = [''] + columns
    if total_col: header_row += ['All']
    table_data = [[str(r)] + [0] * (len(header_row) - 1) for r in rows]
    for row in table_data:
        for i, val in enumerate(data):
            row[i+1] = val.get(row[0], 0)
        if total_col:
            row[-1] = sum(row[1:-1])
    if total_row:
        footer_row = ['Total'] + [0] * (len(header_row) - 1)
        for i in range(len(footer_row)-1):
            footer_row[i+1] = sum([d[i+1] for d in table_data])
    return [header_row] + table_data + [footer_row]


def get_time_scale(filters):
    period = filters.get('time_scale', 'year')
    if period == 'month':
        periods = [i for i in range(1, 13)]
        period_names = [calendar.month_abbr[per].title() for per in periods]
    elif period == 'quarter':
        periods = [1, 2, 3, 4]
        period_names = [f'Q{per}' for per in periods]
    elif period == 'cycle':
        periods = [1, 2]
        period_names = ['Jan-June', 'July-Dec']
    else:
        periods = get_data_periods('year')
        period_names = periods
    return (period, periods, period_names)


def usage_summary(period='year', **all_filters):
    period, periods, period_names = get_time_scale(all_filters)
    filters = {f: val for f, val in all_filters.items() if f != 'time_scale'}

    field = 'created__{}'.format(period)
    created_filters = {f.replace('modified', 'created'): val for f, val in filters.items()}

    ### Sample Stats
    sample_filters = {f.replace('beamline', 'datasets__beamline'): val for f, val in created_filters.items()}
    samples = Sample.objects.filter(**sample_filters)
    sample_counts_info = samples.values(field).order_by(field).annotate(count=Count('id'))

    ### Session Stats
    sessions = Session.objects.filter(**created_filters)
    session_counts_info = sessions.values(field).order_by(field).annotate(count=Count('id'))
    throughput_info = sessions.values(field).order_by(field).annotate(
        num_datasets=Count(Case(When(datasets__kind__name="MX Dataset", then=1), output_field=IntegerField())),
        num_samples=Count('datasets__sample', distinct=True),
        time=Sum(Coalesce('stretches__end', timezone.now()) - F('stretches__start'), distinct=True)
    )
    throughput_types_info = sessions.values(field, 'project__kind__name').order_by(field).annotate(
        num_datasets=Count(Case(When(datasets__kind__name="MX Dataset", then=1), output_field=IntegerField())),
        num_samples=Count('datasets__sample', distinct=True),
        time=Sum(Coalesce('stretches__end', timezone.now()) - F('stretches__start'), distinct=True)
    )
    session_params = sessions.values(field).order_by(field).annotate(
        hours=Sum(Coalesce('stretches__end', timezone.now()) - F('stretches__start')),
        shifts=Sum(ShiftEnd(Coalesce('stretches__end', timezone.now())) - ShiftStart('stretches__start')),
    )

    ### Project Stats
    project_filters = {f.replace('beamline', 'sessions__beamline'): val for f, val in created_filters.items()}
    project_info = sessions.values(field, 'project__name').distinct().order_by(
        field, 'project__name').annotate(count=Count('project__name'))
    new_project_info = Project.objects.filter(**project_filters).values(field, 'name').order_by(
        field, 'name').annotate(count=Count('name'))
    project_type_colors = {
        kind: ColorScheme.Live8[i]
        for i, kind in enumerate(ProjectType.objects.values_list('name', flat=True).order_by('-name'))
    }

    ### Data Stats
    datasets = Data.objects.filter(**filters)
    dataset_info = datasets.values(field).order_by(field).annotate(
        count=Count('id'), exposure=Avg('exposure_time'),
        duration=Sum(F('end_time') - F('start_time'))
    )
    dataset_durations = {entry[field]: entry['duration'].total_seconds() / HOUR_SECONDS for entry in dataset_info}
    data_time_info = datasets.annotate(shift=ShiftIndex('end_time')).values('shift', 'end_time__week_day').order_by(
        'end_time__week_day', 'shift').annotate(count=Count('id'))
    data_project_kind_info = datasets.values('project__kind__name').order_by('project__kind__name').annotate(
        count=Count('id'))
    data_types_info = datasets.values(field, 'kind__name').order_by(field).annotate(count=Count('id'))
    data_types_names = list(DataType.objects.values_list('name', flat=True))

    ### Metrics Overview
    # Distinct Users
    distinct_users = {key: len([entry for entry in project_info if entry[field] == key]) for key in periods}
    # New Users
    new_users = {key: len([e for e in new_project_info if e[field] == key and e['count']]) for key in periods}
    # Samples Measured
    samples_measured = {entry[field]: entry['count'] for entry in sample_counts_info}
    # Sessions
    session_counts = {entry[field]: entry['count'] for entry in session_counts_info}
    # Shifts Used
    shifts_used = {entry[field]: ceil(entry['shifts'].total_seconds() / SHIFT_SECONDS) for entry in session_params}
    # Time Used (hr)
    time_used = {entry[field]: entry['hours'].total_seconds() / HOUR_SECONDS for entry in session_params}
    # Usage Efficiency (%)
    usage_efficiency = {key: time_used.get(key, 0) / (SHIFT * shifts_used.get(key, 1)) for key in periods}
    # Datasets Collected
    dataset_counts = {entry[field]: entry['count'] for entry in dataset_info}
    # Minutes/Dataset
    minutes_per_dataset = {key: dataset_durations.get(key, 0) * 60 / dataset_counts.get(key, 1) for key in periods}
    # Datasets/Hour
    dataset_per_hour = {key: dataset_counts.get(key, 0) / dataset_durations.get(key, 1) for key in periods}
    # Average Exposure (sec)
    dataset_exposure = {entry[field]: round(entry['exposure'], 3) for entry in dataset_info}
    # Samples/Dataset
    samples_per_dataset = {key: samples_measured.get(key, 0) / dataset_counts.get(key, 1) for key in periods}
    # Sample Throughput (/h)
    sample_throughput = {
        entry[field]: 3600. * entry['num_samples'] / entry['time'].total_seconds()
        for entry in throughput_info if entry['time'] and entry['num_samples']
    }
    # MX Dataset Throughput (/h)
    data_throughput = {
        entry[field]: 3600. * entry['num_datasets'] / entry['time'].total_seconds()
        for entry in throughput_info if entry['time'] and entry['num_datasets']
    }

    ### Plots
    # Throughput Plot
    throughput_data = [
        {
            period.title(): period_names[i],
            "Samples": sample_throughput.get(per, 0),
            "MX Datasets": data_throughput.get(per, 0)
        } for i, per in enumerate(periods)
    ]
    # Sample Throughput Plot by Project Kind
    sample_throughput_types = [
        {
            **{period.title(): period_names[i]},
            **{entry['project__kind__name']: entry['time'] and 3600. * entry['num_samples'] / entry['time'].total_seconds() or 0
               for entry in throughput_types_info if entry[field] == per}
        } for i, per in enumerate(periods)
    ]
    # MX Dataset Throughput Plot by Project Kind
    data_throughput_types = [
        {
            **{period.title(): period_names[i]},
            **{entry['project__kind__name']: entry['time'] and 3600. * entry['num_datasets'] / entry['time'].total_seconds() or 0
               for entry in throughput_types_info if entry[field] == per}
        } for i, per in enumerate(periods)
    ]
    # Productivity Plot
    dataset_per_shift = {key: dataset_counts.get(key, 0) / shifts_used.get(key, 1) for key in periods}
    # Datasets by time of week Plot
    day_names = list(calendar.day_abbr)
    dataset_per_day = [
        {
          'Day': day,
          **{
              '{:02d}:00 Shift'.format(entry['shift'] * SHIFT): entry['count']
              for entry in data_time_info if (entry['end_time__week_day'] - 2) % 7 == i
          }
        } for i, day in enumerate(day_names)
    ]
    # Datasets by Project Type Chart
    category_counts = {entry['project__kind__name']: entry['count'] for entry in data_project_kind_info}

    # Data Summary Table and Plot
    data_counts_by_type = {k: {e['kind__name']: e['count'] for e in data_types_info if e[field] == k} for k in periods}
    data_types_data = [
        {
            period.title(): period_names[i],
            **{
                kind: data_counts_by_type.get(key, {}).get(kind, 0) for kind in data_types_names
            }
        } for i, key in enumerate(periods)
    ]
    data_type_table = make_table(data_types_data, period_names, data_types_names)
    # Dataset Type Chart
    data_type_chart = [
        {'label': kind, 'value': sum([e[kind] for e in data_types_data]) } for kind in data_types_names
    ]

    ### Formatting
    period_xvalues = periods
    x_scale = 'linear'
    time_format = ''
    if period == 'month':
        yr = timezone.now().year
        period_names = [calendar.month_abbr[per].title() for per in periods]
        period_xvalues = [datetime.strftime(datetime(yr, per, 1, 0, 0), '%c') for per in periods]
        time_format = '%b'
        x_scale = 'time'
    elif period == 'year':
        period_xvalues = [datetime.strftime(datetime(per, 1, 1, 0, 0), '%c') for per in periods]
        time_format = '%Y'
        x_scale = 'time'

    # Dataset Summary Plot
    period_data = defaultdict(lambda: defaultdict(int))
    for summary in datasets.values(field, 'kind__name').order_by(field).annotate(count=Count('pk')):
        period_data[summary[field]][summary['kind__name']] = summary['count']

    ### User Statistics
    user_session_info = sessions.values(user=F('project__name'), kind=F('project__kind__name')).order_by('user').annotate(
        duration=Sum(Coalesce('stretches__end', timezone.now()) - F('stretches__start'),),
        shift_duration=Sum(ShiftEnd(Coalesce('stretches__end', timezone.now())) - ShiftStart('stretches__start')),
    )
    user_data_info = datasets.values(user=F('project__name')).order_by('user').annotate(count=Count('id'),
        shutters=Sum(F('end_time') - F('start_time'))
    )
    user_sample_info = samples.values(user=F('project__name')).order_by('user').annotate(count=Count('id'))
    user_types = {info['user']: info["kind"] for info in user_session_info}
    user_stats = {}
    # Datasets
    user_stats['datasets'] = [
        {'User': info['user'], 'Datasets': info['count'], 'Type': user_types.get(info['user'], 'Unknown')}
        for info in sorted(user_data_info, key=lambda v: v['count'], reverse=True)[:MAX_COLUMN_USERS]
    ]
    # Samples
    user_stats['samples'] = [
        {'User': info['user'], 'Samples': info['count'], 'Type': user_types.get(info['user'], 'Unknown')}
        for info in sorted(user_sample_info, key=lambda v: v['count'], reverse=True)[:MAX_COLUMN_USERS]
    ]
    # Time Used
    user_stats['time_used'] = [
        {'User': info['user'], 'Hours': round(info["duration"].total_seconds() / HOUR_SECONDS, 1), 'Type': user_types.get(info['user'], 'Unknown')}
        for info in sorted(user_session_info, key=lambda v: v['duration'], reverse=True)[:MAX_COLUMN_USERS]
    ]
    # Efficiency
    user_shutters = {
        info['user']: info["shutters"].total_seconds()
        for info in user_data_info
    }
    user_stats['efficiency'] = [
        {'User': info['user'],
         'Percent': min(100, 100 * user_shutters.get(info['user'], 0) / info["duration"].total_seconds()),
         'Type': user_types.get(info['user'], 'Unknown')}
        for info in sorted(user_session_info,
                           key=lambda v: v['duration'] and user_shutters.get(v['user'], 0) / v['duration'].total_seconds() or 0,
                           reverse=True)[:MAX_COLUMN_USERS]
    ]
    # Schedule Efficiency
    user_stats['schedule_efficiency'] = [
        {'User': info['user'], 'Percent': round(100*info["duration"] / info["shift_duration"], 1),
         'Type': user_types.get(info['user'], 'Unknown')}
        for info in sorted(user_session_info, key=lambda v: v['duration']/v['shift_duration'], reverse=True)[:MAX_COLUMN_USERS]
    ]
    for key, data in user_stats.items():
        user_stats[key] = {
            'x-label': 'User',
            'aspect-ratio': .7,
            'color-by': 'Type',
            'colors': project_type_colors,
            'data': data
        }

    beamtime = {}
    if settings.LIMS_USE_SCHEDULE:
        from basiclive.core.schedule.stats import beamtime_summary

        beamtime = beamtime_summary(**{f.replace('modified', 'start'): val for f, val in all_filters.items()})

    stats = {'details': [
        {
            'title': 'Metrics Overview',
            'style': 'row',
            'content': [
                {
                    'title': 'Usage Statistics',
                    'kind': 'table',
                    'data': [
                        [period.title()] + period_names,
                        ['Distinct Users'] + [distinct_users.get(p, 0) for p in periods],
                        ['New Users'] + [new_users.get(p, 0) for p in periods],
                        ['Samples Measured'] + [samples_measured.get(p, 0) for p in periods],
                        ['Sessions'] + [session_counts.get(p, 0) for p in periods],
                        ['Shifts Used'] + [shifts_used.get(p, 0) for p in periods],
                        ['Time Used¹ (hr)'] + ['{:0.1f}'.format(time_used.get(p, 0)) for p in periods],
                        ['Usage Efficiency² (%)'] + ['{:.0%}'.format(usage_efficiency.get(p, 0)) for p in periods],
                        ['Datasets³ Collected'] + [dataset_counts.get(p, 0) for p in periods],
                        ['Minutes/Dataset³'] + ['{:0.1f}'.format(minutes_per_dataset.get(p, 0)) for p in periods],
                        ['Datasets³/Hour'] + ['{:0.1f}'.format(dataset_per_hour.get(p, 0)) for p in periods],
                        ['Average Exposure (sec)'] + ['{:0.2f}'.format(dataset_exposure.get(p, 0)) for p in periods],
                        ['Samples/Dataset³'] + ['{:0.1f}'.format(samples_per_dataset.get(p, 0)) for p in periods],
                        ['Sample Throughput (/h)'] + ['{:0.2f}'.format(sample_throughput.get(p, 0)) for p in periods],
                        ['MX Dataset Throughput (/h)'] + ['{:0.2f}'.format(data_throughput.get(p, 0)) for p in periods],
                    ],
                    'style': 'col-12',
                    'header': 'column row',
                    'description': 'Summary of time, datasets and usage statistics',
                    'notes': (
                        ' 1. Time Used is the number of hours an active session was running on the beamline.  \n'
                        ' 2. Usage efficiency is the percentage of used shifts during which a session was active.  \n'
                        ' 3. All datasets are considered for this statistic irrespective of dataset type.'
                    )
                },
                {
                    'title': 'Throughput by {} (/h)'.format(period),
                    'kind': 'columnchart',
                    'data': {
                        'x-label': period.title(),
                        'data': throughput_data,
                    },
                    'style': 'col-12 col-md-6'
                },
                {
                    'title': 'Sample Throughput by {} (/h)'.format(period),
                    'kind': 'columnchart',
                    'data': {
                        'x-label': period.title(),
                        'data': sample_throughput_types,
                        'colors': project_type_colors
                    },
                    'style': 'col-12 col-md-6'
                },
                {
                    'title': 'MX Dataset Throughput by {} (/h)'.format(period),
                    'kind': 'columnchart',
                    'data': {
                        'x-label': period.title(),
                        'data': data_throughput_types,
                        'colors': project_type_colors
                    },
                    'style': 'col-12 col-md-6'
                },
                {
                    'title': 'Usage Statistics',
                    'kind': 'columnchart',
                    'data': {
                        'x-label': period.title(),
                        'data': [
                            {
                                period.title(): period_names[i],
                                'Samples': samples_measured.get(per, 0),
                                'Datasets': dataset_counts.get(per, 0),
                                'Total Time': round(time_used.get(per, 0), 1),
                            } for i, per in enumerate(periods)
                        ]
                    },
                    'style': 'col-12 col-md-6'
                },
                {
                    'title': 'Productivity',
                    'kind': 'lineplot',
                    'data':
                        {
                            'x': [period.title()] + period_xvalues,
                            'y1': [['Datasets/Shift'] + [round(dataset_per_shift.get(per, 0), 2) for per in periods]],
                            'y2': [['Average Exposure'] + [round(dataset_exposure.get(per, 0), 2) for per in periods]],
                            'x-scale': x_scale,
                            'time-format': time_format
                        },
                    'style': 'col-12 col-md-6',
                },
                {
                    'title': 'Datasets by time of week',
                    'kind': 'columnchart',
                    'data': {
                        'x-label': 'Day',
                        'data': dataset_per_day
                    },
                    'style': 'col-12 col-md-6'
                },
                {
                    'title': 'Datasets by Project Type',
                    'kind': 'pie',
                    'data': {
                        'data': [
                            {'label': key or 'Unknown', 'value': count} for key, count in category_counts.items()
                        ],
                    },
                    'style': 'col-12 col-md-6'
                },
            ]
        },
        {
            'title': 'Data Summary',
            'style': "row",
            'content': [
                {
                    'title': 'Dataset summary by {}'.format(period),
                    'kind': 'table',
                    'data': data_type_table,
                    'header': 'column row',
                    'style': 'col-12'
                },
                {
                    'title': 'Dataset summary by {}'.format(period),
                    'kind': 'columnchart',
                    'data': {
                        'x-label': period.title(),
                        'stack': [data_types_names],
                        'data': data_types_data,
                    },
                    'style': 'col-12 col-md-6'
                },
                {
                    'title': 'Dataset Types',
                    'kind': 'pie',
                    'data': {
                        "colors": "Live16",
                        "data": data_type_chart,
                    },
                    'style': 'col-12 col-md-6'
                }
            ]
        },
        {
            'title': 'User Statistics',
            'style': "row",
            'content': [
                {
                    'title': 'Datasets',
                    'kind': 'barchart',
                    'data': user_stats['datasets'],
                    'notes': (
                        "Dataset counts include all types of datasets. "
                        "Only the top {} users by number of datasets are shown"
                    ).format(MAX_COLUMN_USERS),
                    'style': 'col-12 col-md-4'
                },
                {
                    'title': 'Samples',
                    'kind': 'barchart',
                    'data': user_stats['samples'],
                    'notes': (
                        "Sample counts include only samples measured on the beamline. "
                        "Only the top {} users sample count shown"
                    ).format(MAX_COLUMN_USERS),
                    'style': 'col-12 col-md-4'
                },
                {
                    'title': 'Time Used',
                    'kind': 'barchart',
                    'data': user_stats['time_used'],
                    "notes": (
                        "Total time is sum of active session durations for each user. Only the top {} "
                        "users are shown."
                    ).format(MAX_COLUMN_USERS),
                    'style': 'col-12 col-md-4'
                },
                {
                    'title': 'Efficiency',
                    'kind': 'barchart',
                    'data': user_stats['efficiency'],
                    "notes": (
                        "Efficiency is the percentage of Time Used during which shutters were open. This measures how "
                        "effectively users are using their active session for data collection. "
                        "Only the top {} users are shown."
                    ).format(MAX_COLUMN_USERS),
                    'style': 'col-12 col-md-4'
                },
                {
                    'title': 'Schedule Efficiency',
                    'kind': 'barchart',
                    'data': user_stats['schedule_efficiency'],
                    "notes": (
                        "Schedule Efficiency is the percentage of shift time during which a session "
                        "was active. This measures how effectively users are using full scheduled shifts for "
                        "data collection. Only the top {} users are shown."
                    ).format(MAX_COLUMN_USERS),
                    'style': 'col-12 col-md-4'
                },
            ],
        },
    ] + beamtime
    }
    return stats


# Histogram Parameters
PARAMETER_NAMES = {
    field_name: Data._meta.get_field(field_name).verbose_name
    for field_name in ['exposure_time', 'attenuation', 'energy', 'num_frames']
}

PARAMETER_NAMES.update({
    field_name: AnalysisReport._meta.get_field(field_name).verbose_name
    for field_name in ('score',)
})

PARAMETER_RANGES = {
    'exposure_time': (0.01, 20),
    'score': (0.01, 1),
    'energy': (4., 18.)
}

PARAMETER_BINNING = {
    'energy': 8,
    'attenuation': numpy.linspace(0, 100, 11)
}


def get_histogram_points(data, range=None, bins='doane'):
    counts, edges = numpy.histogram(data, bins=bins, range=range)
    centers = (edges[:-1] + edges[1:]) * 0.5
    return list(zip(centers, counts))


def make_parameter_histogram(data_info, report_info):
    """
    Create a histogram for parameters in the query results
    :param data_info: Query result for data
    :param report_info: Query result for reports
    :return: histogram data
    """
    histograms = {
        field_name: get_histogram_points(
            [float(d[field_name]) for d in data_info if d[field_name] is not None],
            range=PARAMETER_RANGES.get(field_name), bins=PARAMETER_BINNING.get(field_name, 'doane')
        )
        for field_name in ('exposure_time', 'attenuation', 'energy', 'num_frames')
    }
    histograms['score'] = get_histogram_points(
        [float(d['score']) for d in report_info if d['score'] > -0.1],
        range=PARAMETER_RANGES.get('score')
    )
    return histograms


def parameter_summary(**filters):
    beam_sizes = Data.objects.filter(beam_size__isnull=False, **filters).values(
        'beam_size').order_by('beam_size').annotate(
        count=Count('id')
    )
    report_filters = {f.replace('beamline', 'data__beamline'): val for f, val in filters.items()}

    report_info = AnalysisReport.objects.filter(**report_filters).values('score')
    data_info = Data.objects.filter(**filters).values('exposure_time', 'attenuation', 'energy',
                                                                         'num_frames')
    param_histograms = make_parameter_histogram(data_info, report_info)

    stats = {'details': [
        {
            'title': 'Parameter Distributions',
            'style': 'row',
            'content': [
                           {
                               'title': 'Beam Size',
                               'kind': 'pie',
                               'data': {
                                   'data': [
                                       {'label': "{:0.0f}".format(entry['beam_size']), 'value': entry['count']}
                                       for entry in beam_sizes
                                   ]
                               },
                               'style': 'col-12 col-md-6'
                           },
                       ] + [
                           {
                               'title': PARAMETER_NAMES[param].title(),
                               'kind': 'histogram',
                               'data': {
                                   'data': [
                                       {"x": row[0], "y": row[1]} for row in param_histograms[param]
                                   ],
                               },
                               'style': 'col-12 col-md-6'
                           } for param in ('score', 'energy', 'exposure_time', 'attenuation', 'num_frames')
                       ]
        }
    ]}
    return stats


def session_stats(session):
    data_extras = session.datasets.values(key=F('kind__name')).order_by('key').annotate(
        count=Count('id'), time=Sum(F('exposure_time') * F('num_frames'), output_field=FloatField()),
        frames=Sum('num_frames'),
    )

    data_stats = [
        ['Avg Frames/{}'.format(info['key']), round(info['frames'] / info['count'], 1)]
        for info in data_extras
    ]
    data_counts = [
        [info['key'], round(info['count'], 1)]
        for info in data_extras
    ]

    data_info = session.datasets.values('exposure_time', 'attenuation', 'energy', 'num_frames')
    report_info = AnalysisReport.objects.filter(data__session=session).values('score')
    param_histograms = make_parameter_histogram(data_info, report_info)

    shutters = sum([info['time'] for info in data_extras]) / HOUR_SECONDS
    total_time = session.total_time()
    last_data = session.datasets.last()

    timeline_data = [
        {
            "type": data['kind__name'],
            "start": js_epoch(data['start_time']),
            "end": js_epoch(data['end_time']),
            "label": "{}: {}".format(data["kind__name"], data['name'])
        }
        for data in session.datasets.values('start_time', 'end_time', 'kind__name', 'name')
    ]
    stats = {'details': [
        {
            'title': 'Session Parameters',
            'description': 'Data Collection Summary',
            'style': "row",
            'content': [
                           {
                               'title': '',
                               'kind': 'table',
                               'data': [
                                           ['Total Time', humanize_duration(total_time)],
                                           ['First Login', timezone.localtime(session.start()).strftime('%c')],
                                           ['Samples', session.samples().count()],
                                       ] + data_counts,
                               'header': 'column',
                               'style': 'col-12 col-md-6',
                           },
                           {
                               'title': '',
                               'kind': 'table',
                               'data': [
                                           ['Shutters Open', "{} ({:.2f}%)".format(
                                               humanize_duration(shutters),
                                               shutters * 100 / total_time if total_time else 0)
                                            ],
                                           ['Last Dataset', '' if not last_data else last_data.modified.strftime('%c')],
                                           ['No. of Logins', session.stretches.count()],
                                       ] + data_stats,
                               'header': 'column',
                               'style': 'col-12 col-md-6',
                           },
                           {
                               'title': 'Types of data collected',
                               'kind': 'columnchart',
                               'data': {
                                   'x-label': 'Data Type',
                                   'data': [{
                                       'Data Type': row['key'],
                                       'Total': row['count'],
                                   }
                                       for row in data_extras
                                   ]
                               },
                               'style': 'col-12 col-md-6'
                           }

                       ] + [
                           {
                               'title': PARAMETER_NAMES[param].title(),
                               'kind': 'histogram',
                               'data': {
                                   'data': [
                                       {"x": row[0], "y": row[1]} for row in param_histograms[param]
                                   ],
                               },
                               'style': 'col-12 col-md-6'
                           } for param in ('score', 'energy', 'exposure_time', 'attenuation', 'num_frames')
                       ] + [

                       ]
        },
        {
            'title': 'Session Timeline',
            'description': (
                'Timeline of data collection for various types of '
                'datasets during the whole session from {} to {}'
            ).format(session.start().strftime('%c'), session.end().strftime('%c')),
            'style': "row",
            'content': [
                {
                    'title': 'Session Timeline',
                    'kind': 'timeline',
                    'start': js_epoch(session.start()),
                    'end': js_epoch(session.end()),
                    'data': timeline_data,
                    'style': 'col-12'
                },
                {
                    'title': 'Inactivity Gaps',
                    'kind': 'table',
                    'data': [
                                ['', 'Start', 'End', 'Duration']] + [
                                [i + 1, gap[0].strftime('%c'), gap[1].strftime('%c'), natural_duration(gap[2])]
                                for i, gap in enumerate(session.gaps())
                            ],
                    'header': 'row',
                    'notes': "Periods of possible inactivity while the session was open, greater than 10 minutes",
                    'style': 'col-12',
                },

            ]

        }

    ]}
    return stats


def project_stats(project, **filters):
    period = 'year'
    periods = get_data_periods()
    field = 'created__{}'.format(period)

    session_counts_info = project.sessions.filter(**filters).values(field).order_by(field).annotate(count=Count('id'))
    session_params = project.sessions.filter(**filters).values(field).order_by(field).annotate(
        shift_duration=Sum(
            ShiftEnd(Coalesce('stretches__end', timezone.now())) - ShiftStart('stretches__start')
        ),
        duration=Sum(
            Coalesce('stretches__end', timezone.now()) - F('stretches__start'),
        ),
    )

    session_counts = {
        entry[field]: entry['count']
        for entry in session_counts_info
    }
    session_shifts = {
        entry[field]: ceil(entry['shift_duration'].total_seconds() / SHIFT_SECONDS)
        for entry in session_params
    }
    session_hours = {
        entry[field]: entry['duration'].total_seconds() / HOUR_SECONDS
        for entry in session_params
    }

    session_efficiency = {
        key: session_hours.get(key, 0) / (SHIFT * session_shifts.get(key, 1))
        for key in periods
    }

    data_params = project.datasets.filter(**filters).values(field).order_by(field).annotate(
        count=Count('id'), exposure=Avg('exposure_time'),
        duration=Sum(F('end_time') - F('start_time'))
    )

    dataset_counts = {
        entry[field]: entry['count']
        for entry in data_params
    }
    dataset_exposure = {
        entry[field]: round(entry['exposure'], 3)
        for entry in data_params
    }

    dataset_durations = {
        entry[field]: entry['duration'].total_seconds() / HOUR_SECONDS
        for entry in data_params
    }

    dataset_per_shift = {
        key: dataset_counts.get(key, 0) / session_shifts.get(key, 1)
        for key in periods
    }

    dataset_per_hour = {
        key: dataset_counts.get(key, 0) / dataset_durations.get(key, 1)
        for key in periods
    }

    minutes_per_dataset = {
        key: dataset_durations.get(key, 0) * 60 / dataset_counts.get(key, 1)
        for key in periods
    }
    sample_counts = {
        entry[field]: entry['count']
        for entry in
        project.samples.filter(**filters).values(field).order_by(field).annotate(count=Count('id'))
    }
    samples_per_dataset = {
        key: sample_counts.get(key, 0) / dataset_counts.get(key, 1)
        for key in periods
    }

    data_types = project.datasets.filter(**filters).values('kind__name').order_by('kind__name').annotate(
        count=Count('id'))

    shift_params = project.datasets.filter(**filters).annotate(shift=ShiftIndex('end_time')).values(
        'shift', 'end_time__week_day').order_by('end_time__week_day', 'shift').annotate(count=Count('id'))

    day_shift_counts = defaultdict(dict)
    day_names = list(calendar.day_abbr)
    for entry in shift_params:
        day = calendar.day_abbr[(entry['end_time__week_day'] - 2) % 7]
        day_part = '{:02d}:00 Shift'.format(entry['shift'] * SHIFT)
        day_shift_counts[day][day_part] = entry['count']
        day_shift_counts[day]['Day'] = day

    shifts = sum(session_shifts.values())
    ttime = sum(session_hours.values())
    shutters = sum(dataset_durations.values())

    period_data = defaultdict(lambda: defaultdict(int))
    for summary in project.datasets.filter(**filters).values(field, 'kind__name').annotate(count=Count('pk')):
        period_data[summary[field]][summary['kind__name']] = summary['count']
    datatype_table = []
    for item in data_types:
        kind_counts = [period_data[per][item['kind__name']] for per in periods]
        datatype_table.append([item['kind__name']] + kind_counts + [sum(kind_counts)])
    period_counts = [sum(period_data[per].values()) for per in periods]
    datatype_table.append(['Total'] + period_counts + [sum(period_counts)])
    chart_data = []

    period_names = periods
    if period == 'month':
        yr = timezone.now().year
        period_names = [calendar.month_abbr[per].title() for per in periods]
        period_xvalues = [datetime.strftime(datetime(yr, per, 1, 0, 0), '%c') for per in periods]
        time_format = '%b'
        x_scale = 'time'
    elif period == 'year':
        period_xvalues = [datetime.strftime(datetime(per, 1, 1, 0, 0), '%c') for per in periods]
        time_format = '%Y'
        x_scale = 'time'

    # data histogram
    for i, per in enumerate(periods):
        series = {'Year': period_names[i]}
        series.update(period_data[per])
        chart_data.append(series)

    last_session = project.sessions.last()
    first_session = project.sessions.first()
    actual_time = 0 if not shifts else ttime / (shifts * SHIFT)
    first_session_time = "Never" if not first_session else '{} ago'.format(timesince(first_session.created))
    last_session_time = "Never" if not first_session else '{} ago'.format(timesince(last_session.created))

    sessions_total = ['Sessions', sum(session_counts.values())]
    shifts_used_total = ['Shifts Used', '{} ({})'.format(shifts, humanize_duration(shifts * SHIFT))]

    beamtime = []
    visits = []
    stat_table = []
    if settings.LIMS_USE_SCHEDULE:

        sched_field = field.replace('created', 'start')
        beamtime_counts = {
            e[sched_field]: e['count']
            for e in project.beamtime.filter(**filters, cancelled=False).values(sched_field).annotate(count=Count('id'))
        }
        beamtime_shifts = {
            e[sched_field]: ceil(e['shift_duration'].total_seconds() / SHIFT_SECONDS)
            for e in project.beamtime.filter(**filters, cancelled=False).with_duration().values(sched_field, 'shift_duration').order_by(sched_field)
        }
        visits = ['Visits Scheduled'] + [beamtime_counts.get(p, 0) for p in periods]
        beamtime = ['Shifts Scheduled'] + [beamtime_shifts.get(p, 0) for p in periods]
        scheduled_shifts = sum(beamtime_shifts.values())

        time_table = [
            ['Visits Scheduled', sum(beamtime_counts.values())],
            ['Shifts Scheduled', '{} ({})'.format(scheduled_shifts, humanize_duration(scheduled_shifts * SHIFT))],
            shifts_used_total
        ]
        stat_table = [sessions_total,]
    else:
        time_table = [
            shifts_used_total,
            sessions_total,
        ]

    stats = {'details': [
        {
            'title': 'Data Collection Summary',
            'style': "row",
            'content': [
                {
                    'title': 'Time Usage',
                    'kind': 'table',
                    'data': time_table + [
                        ['Actual Time', '{:0.0%} ({})'.format(actual_time, humanize_duration(ttime))],
                        ['Shutters Open', '{}'.format(humanize_duration(shutters))],
                    ],
                    'header': 'column',
                    'style': 'col-sm-6'
                },
                {
                    'title': 'Overall Statistics',
                    'kind': 'table',
                    'data': stat_table + [
                        ['First Session', last_session_time],
                        ['Last Session', first_session_time],
                        ['Shipments / Containers', "{} / {}".format(
                            project.shipments.count(),
                            project.containers.filter(status__gte=Container.STATES.ON_SITE).count()
                        )],
                        ['Groups / Samples', "{} / {}".format(
                            project.sample_groups.filter(shipment__status__gte=Shipment.STATES.ON_SITE).count(),
                            project.samples.filter(container__status__gte=Container.STATES.ON_SITE).count())],
                    ],
                    'header': 'column',
                    'style': 'col-sm-6'
                },
                {
                    'title': 'Usage Statistics',
                    'kind': 'table',
                    'data': [
                        ["Year"] + period_names,
                        ['Samples Measured'] + [sample_counts.get(p, 0) for p in periods],
                        ['Sessions'] + [session_counts.get(p, 0) for p in periods],
                        visits,
                        beamtime,
                        ['Shifts Used'] + [session_shifts.get(p, 0) for p in periods],
                        ['Time Used¹ (hr)'] + ['{:0.1f}'.format(session_hours.get(p, 0)) for p in periods],
                        ['Usage Efficiency² (%)'] + ['{:.0%}'.format(session_efficiency.get(p, 0)) for p in periods],
                        ['Datasets³ Collected'] + [dataset_counts.get(p, 0) for p in periods],
                        ['Minutes/Dataset³'] + ['{:0.1f}'.format(minutes_per_dataset.get(p, 0)) for p in periods],
                        ['Datasets³/Hour'] + ['{:0.1f}'.format(dataset_per_hour.get(p, 0)) for p in periods],
                        ['Average Exposure (sec)'] + ['{:0.2f}'.format(dataset_exposure.get(p, 0)) for p in periods],
                        ['Samples/Dataset³'] + ['{:0.1f}'.format(samples_per_dataset.get(p, 0)) for p in periods],

                    ],
                    'style': 'col-12',
                    'header': 'column row',
                    'description': 'Summary of time, datasets and usage statistics',
                    'notes': (
                        ' 1. Time Used is the number of hours an active session was running on the beamline.  \n'
                        ' 2. Usage efficiency is the percentage of used shifts during which a session was active.  \n'
                        ' 3. All datasets are considered for this statistic irrespective of dataset type.'
                    )
                },
                {
                    'title': 'Usage Statistics',
                    'kind': 'columnchart',
                    'data': {
                        'x-label': period.title(),
                        'colors': 'Live8',
                        'data': [
                            {
                                period.title(): period_names[i],
                                'Samples': sample_counts.get(per, 0),
                                'Datasets': dataset_counts.get(per, 0),
                                'Total Time': round(session_hours.get(per, 0), 1),
                            } for i, per in enumerate(periods)
                        ]
                    },
                    'style': 'col-12 col-md-6'
                },
                {
                    'title': 'Productivity',
                    'kind': 'lineplot',
                    'data':
                        {
                            'x': [period.title()] + period_xvalues,
                            'y1': [['Datasets/Shift'] + [round(dataset_per_shift.get(per, 0), 2) for per in periods]],
                            'y2': [['Average Exposure'] + [round(dataset_exposure.get(per, 0), 2) for per in periods]],
                            'x-scale': x_scale,
                            'time-format': time_format
                        },
                    'style': 'col-12 col-md-6',
                },
            ]
        }
    ]}
    return stats

