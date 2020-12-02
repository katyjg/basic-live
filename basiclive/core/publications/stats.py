import calendar
from datetime import datetime

from django.db.models import Count, Sum, F, Avg, FloatField, Q
from django.db.models.functions import Coalesce
from django.utils import timezone


from .models import Publication, Journal, SubjectArea, Deposition, Metric


class ColorScheme(object):
    Live4 = ["#8f9f9a", "#c56052", "#9f6dbf", "#a0b552"]
    Live8 = ["#073B4C", "#06D6A0", "#FFD166", "#EF476F", "#118AB2", "#7F7EFF", "#afc765", "#78C5E7"]
    Live16 = [
        "#67aec1", "#c45a81", "#cdc339", "#ae8e6b", "#6dc758", "#a084b6", "#667ccd", "#cd4f55",
        "#805cd6", "#cf622d", "#a69e4c", "#9b9795", "#6db586", "#c255b6", "#073B4C", "#FFD166",
    ]


def js_epoch(dt):
    return int("{:0.0f}000".format(dt.timestamp() if dt else datetime.now().timestamp()))


def get_entry(field, entry):
    return {k: v for k, v in entry.items() if k != field}


def get_publications_periods(period='year'):
    field = 'published__{}'.format(period)
    return sorted(Publication.objects.values_list(field, flat=True).distinct())


def publication_stats(period='year', year=None, tag=None):
    field = 'published__{}'.format(period)
    periods = get_publications_periods(period=period)

    period_names = periods
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

    filters = {}
    if year:
        filters['published__year'] = year
    if tag:
        filters['tags__name'] = tag

    full_metrics = Publication.objects.filter(**filters).aggregate(
        total=Count('id'),
        num_cites=Coalesce(Sum('metrics__citations'), 0),
        avg_cites=Coalesce(Avg('metrics__citations'), 0),
        num_mentions=Coalesce(Sum('metrics__mentions'), 0),
        avg_mentions=Coalesce(Avg('metrics__mentions'), 0),
        avg_impact=Coalesce(Avg('journal__metrics__impact_factor'), 0),
        avg_hindex=Coalesce(Avg('journal__metrics__h_index'), 0),
        avg_sjr=Coalesce(Avg('journal__metrics__sjr_rank'), 0),
        avg_quartile=Coalesce(Avg('journal__metrics__sjr_quartile'), 0)
    )

    top_ten_cited = Publication.objects.filter(metrics__isnull=False, **filters).order_by('-metrics__citations')[:10]
    top_ten_mentioned = Publication.objects.filter(metrics__isnull=False, **filters).order_by('-metrics__mentions')[:10]


    metrics = {
        entry[field]: get_entry(field, entry)
        for entry in
        Publication.objects.filter(**filters).values(field).order_by(field).annotate(
            total=Count('id'),
            num_cites=Coalesce(Sum('metrics__citations'), 0),
            avg_cites=Coalesce(Avg('metrics__citations'), 0),
            num_mentions=Coalesce(Sum('metrics__mentions'), 0),
            avg_mentions=Coalesce(Avg('metrics__mentions'), 0),
            avg_impact=Coalesce(Avg('journal__metrics__impact_factor'), 0),
            avg_hindex=Coalesce(Avg('journal__metrics__h_index'), 0),
            avg_sjr=Coalesce(Avg('journal__metrics__sjr_rank'), 0),
            avg_quartile=Coalesce(Avg('journal__metrics__sjr_quartile'), 0)
        )
    }

    filters = {}
    if year:
        filters['released__year'] = year
    if tag:
        filters['tags__name'] = tag

    field = 'released__{}'.format(period)
    full_metrics['depositions'] = Deposition.objects.filter(**filters).count()
    depositions = {
        entry[field]: entry
        for entry in Deposition.objects.filter(**filters).values(field).order_by(field).annotate(
            total=Count('id')
        )
    }

    field = 'collected__{}'.format(period)
    collections = {
        entry[field]: get_entry(field, entry)
        for entry in
        Deposition.objects.filter(collected__isnull=False, **filters).values(field).order_by(field).annotate(
            total=Count('id')

        )
    }

    all_name = 'All' if period == 'year' else year

    stats = {'details': [
        {
            'title': 'Publication Metrics',
            'style': 'row',
            'content': [
                {
                    'title': 'Metrics Summary',
                    'kind': 'table',
                    'data': [
                        [period.title()] + period_names + [all_name],
                        ['Publications'] + [metrics.get(p, {}).get('total', 0) for p in periods] + [full_metrics['total']],
                        ['PDB Depositions'] + [depositions.get(p, {}).get('total', 0) for p in periods] + [full_metrics['depositions']],
                        ['Citations'] + [metrics.get(p, {}).get('num_cites', 0) for p in periods] + [full_metrics['num_cites']],
                        ['Citations/Article'] + [round(metrics.get(p, {}).get('avg_cites', 0), 1) for p in periods] + [round(full_metrics['avg_cites'], 1)],
                        ['Media Mentions¹'] + [metrics.get(p, {}).get('num_mentions', 0) for p in periods] + [full_metrics['num_mentions']],
                        ['Mentions/Article'] + [round(metrics.get(p, {}).get('avg_mentions', 0), 1) for p in periods] + [round(full_metrics['avg_mentions'], 1)],
                        ['Average Impact Factor²'] + [round(metrics.get(p, {}).get('avg_impact', 0), 1) for p in periods] + [round(full_metrics['avg_impact'], 1)],
                        ['Average SJR³'] + [round(metrics.get(p, {}).get('avg_sjr', 0), 1) for p in periods] + [round(full_metrics['avg_sjr'], 1)],
                        ['Average SJR³ Quartile'] + [round(metrics.get(p, {}).get('avg_quartile', 0), 1) for p in periods] + [round(full_metrics['avg_quartile'], 1)],
                        ['Average H-Index'] + [round(metrics.get(p, {}).get('avg_hindex', 0), 1) for p in periods] + [round(full_metrics['avg_hindex'], 1)],
                    ],
                    'style': 'col-12',
                    'header': 'column row',
                    'description': 'Summary of publication metrics statistics',
                    'notes': (
                        ' 1. Mentions represent the number of news stories, and social media mentions the reference the publication.\n'
                        ' 2. The Average Impact Factor is the ratio of citations to the number of citable documents for '
                        'the journal over the previous two years. This value is calculated based on citations in the SCOPUS database '
                        'and may be different from the Web Of Science values from the Thomson Reuters database.\n'
                        ' 3. SJR is the SCIMAGO Journal Rank Metric: https://www.scimagojr.com/. '
                        ' A Journal with an SJR quartile of 1 is in the top 25% of journals in the field when ranked by SJR, and '
                        ' a quartile of 2 is ranked higher than 50% but lower than 25% of journals in the field.'
                    )
                },
                {
                    'title': 'Research Output',
                    'kind': 'columnchart',
                    'data': {
                        'x-label': period.title(),
                        'data': [
                            {
                                period.title(): period_names[i],
                                'Publications': metrics.get(per, {}).get('total', 0),
                                'Depositions': depositions.get(per, {}).get('total', 0)
                            } for i, per in enumerate(periods)
                        ]
                    },
                    'style': 'col-12 col-md-6'
                },
                {
                    'title': 'Data Collection vs PDB Release',
                    'kind': 'lineplot',
                    'data':
                        {
                            'x': [period.title()] + period_xvalues,
                            'y1': [
                                ['Data Collection'] + [round(collections.get(per, {}).get('total', 0), 2) for per in periods],
                                ['PDB Release'] + [round(depositions.get(per, {}).get('total', 0), 2) for per in periods],
                            ],
                            'x-scale': x_scale,
                            'time-format': time_format
                        },
                    'style': 'col-12 col-md-6',
                },
                {
                    'title': 'Top 10 Most Cited Articles',
                    'kind': 'table',
                    'data': [
                        ['Citations', 'Article']
                    ] + [
                        [pub.metrics.citations, pub.cite()]
                        for pub in top_ten_cited
                    ],
                    'style': 'col-12',
                    'header': 'row',
                },
                {
                    'title': 'Top 10 Most Mentioned Articles',
                    'kind': 'table',
                    'data': [
                        ['Mentions', 'Article']
                    ] + [
                        [pub.metrics.mentions, pub.cite()]
                        for pub in top_ten_mentioned
                    ],
                    'style': 'col-12',
                    'header': 'row',
                },
            ]
        },
    ]
    }
    return stats


def h_indices(users):
    h_indices = {}
    for user in users:
        publications = Publication.objects.filter(metrics__citations__isnull=False, authors__icontains=user.last_name)
        citations = publications.order_by('-metrics__citations').values_list('metrics__citations', flat=True)
        h_indices[user.username] = len([c for i, c in enumerate(citations) if c >= (i + 1)])
    return h_indices
