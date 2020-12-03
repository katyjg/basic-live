import calendar
from datetime import timedelta

from django.db.models import Count, Sum, F, Case, When, IntegerField, Q, DateTimeField, ExpressionWrapper
from django.template.defaultfilters import linebreaksbr

from basiclive.core.lims.models import Session
from basiclive.core.lims.stats import js_epoch
from .models import SupportArea, AreaFeedback, SupportRecord, LikertScale


def avg_diff(td):
    diffs = [abs(td[i]['created'] - td[i - 1]['end']).total_seconds()/3600 for i in range(1, len(td))]
    return len(td) > 1 and (sum(diffs)/(len(td) - 1)) or None


def supportrecord_stats(objlist, filters):
    support_fltrs = {"{}{}".format('help__', k): v for k, v in filters.items()}
    support_areas = SupportArea.objects.filter(pk__in=objlist.values_list('areas__pk', flat=True)).annotate(
        info=Count(Case(When(help__kind='info', then=1), output_field=IntegerField()), filter=Q(**support_fltrs)),
        problem=Count(Case(When(help__kind='problem', then=1), output_field=IntegerField()), filter=Q(**support_fltrs)),
        time_lost=Sum('help__lost_time', filter=Q(**support_fltrs))
    ).order_by('pk').values('name', 'info', 'problem', 'time_lost', 'external')

    lost_time = {
        'Overall': sum([a['time_lost'] for a in support_areas]),
        'Beamline Overall': sum([a['time_lost'] for a in support_areas if not a['external']])
    }
    total_interactions = sum([a['info'] + a['problem'] for a in support_areas])
    support_areas = sorted(support_areas, key=lambda x: -(x['info'] + x['problem']))
    area_interactions = [
        {
            "Area": area['name'],
            "Info": area['info'],
            "Problem": area['problem'],
            "Interactions (%)": 100 * sum(a['info'] + a['problem'] for a in support_areas[:i+1]) / total_interactions
        } for i, area in enumerate(support_areas)
    ]

    fails = objlist.filter(kind__iexact='problem').annotate(
        end=ExpressionWrapper(F('created') + timedelta(hours=1) * F('lost_time'), output_field=DateTimeField())
    )
    mtbf_overall = avg_diff(list(fails.order_by('created').values('created', 'end')))
    mtbf_beamline = avg_diff(list(fails.exclude(areas__external=True).order_by('created').values('created', 'end')))

    mtbf = {
        **{
            'Overall': mtbf_overall,
            'Beamline Overall': mtbf_beamline,
        }, **{
            a['name']: avg_diff(list(fails.filter(areas__name=a['name']).order_by('created').values('created', 'end')))
            for a in support_areas
        }
    }
    timeline_data = [
        {
            "type": data['kind'],
            "start": js_epoch(data['created']),
            "end": js_epoch(data['created'] + timedelta(minutes=min(60 * data['lost_time'], 1))),
            "label": "{}".format(data["kind"])
        }
        for data in objlist.values('created', 'lost_time', 'kind')
    ]
    total_rows = []
    for name, sa in [('Overall', support_areas), ('Beamline Overall', [s for s in support_areas if not s['external']])]:
        total_rows.append([
            name,
            sum([a['info'] for a in sa]),
            sum([a['problem'] for a in sa]),
            mtbf[name] is not None and round(mtbf[name], 2) or '-',
            round(lost_time[name] / max(sum([a['problem'] for a in sa]), 1), 2),
            round(sum([a['time_lost'] for a in sa]), 2)
        ])
    stats = {'details': [
        {
            'title': 'User Support Interactions and Problem Recovery',
            'description': 'Summary of user support records',
            'style': "row",
            'content': [
                {
                    'title': 'Support Records by Area',
                    'kind': 'table',
                    'header': 'row column',
                    'data': [['', 'Info', 'Problem', 'MTBF¹ (h)', 'MRT² (h)', 'Time Lost (h)']] +
                            [['{}{}'.format(area['external'] and '[*] ' or '', area['name']),
                              area['info'], area['problem'],
                              mtbf[area['name']] is not None and round(mtbf[area['name']], 2) or '-',
                              area['problem'] and round(area['time_lost'] / area['problem'], 2) or '-',
                              area['time_lost']]
                             for area in sorted(support_areas, key=lambda i: -i['time_lost'])
                             ] +
                            total_rows,
                    'notes': """<dl>
                            <dd><strong>[*] External Area:</strong> External factor out of the beamline's control; 
                            excluded from <strong>Beamline Overall</strong> calculations</dd>
                            <dd><strong>[1] MTBF:</strong> Mean Time Between Failures</dd>
                            <dd><strong>[2] MRT:</strong> Mean Recovery Time</dd>
                        </dl>""",
                    'style': 'col-12'
                },
                {
                    'title': 'User Support Interactions and Lost Time',
                    'kind': 'columnchart',
                    'data': {
                        'aspect-ratio': 2,
                        'colors': {"Info": '#66ffd5', "Lost Time (hours)": '#ffa333', "Problem": '#ffdd33'},
                        'x-label': "Area",
                        'data': [
                            {
                                "Area": area['name'],
                                "Info": area['info'],
                                "Problem": area['problem'],
                                "Lost Time (hours)": area['time_lost'] or 0,
                            } for area in support_areas
                        ]
                    },
                    'style': 'col-12'
                },
                {
                    'title': 'User Support Areas by Interaction',
                    'kind': 'columnchart',
                    'data': {
                        'aspect-ratio': 2,
                        'colors': {"Info": '#66ffd5',
                                   "Lost Time (hours)": '#ffa333',
                                   "Problem": '#ffdd33',
                                   "Interactions (%)": '#777777'},
                        'x-label': "Area",
                        'line-limits': [0, 100],
                        'line': "Interactions (%)",
                        'stack': [["Info", "Problem"]],
                        'data': area_interactions
                    },
                    'style': 'col-12'
                },
                {
                    'title': 'User Support Areas by Lost Time',
                    'kind': 'columnchart',
                    'data': {
                        'aspect-ratio': 2,
                        'colors': {"Lost Time (hours)": '#ffa333', "Percentage (%)": '#777777'},
                        'x-label': "Area",
                        'line': "Percentage (%)",
                        'line-limits': [0, 100],
                        'data': [
                            {
                                "Area": area['name'],
                                "Lost Time (hours)": area['time_lost'] or 0,
                                "Percentage (%)": lost_time['Overall'] and 100 * sum([
                                    a['time_lost'] for a in sorted(support_areas, key=lambda i: -i['time_lost'])[:j + 1]
                                ]) / lost_time['Overall'] or 0
                            } for j, area in enumerate(sorted(support_areas, key=lambda i: -i['time_lost']))
                        ]
                    },
                    'style': 'col-12'
                },
                {
                    'title': 'User Support Interactions Staff Comments',
                    'notes': '<strong>Staff Comments:</strong>\n\n' + linebreaksbr(
                        '\n\n'.join(SupportRecord.objects.values_list('staff_comments', flat=True).distinct())),
                    'style': 'col-12'
                },
                objlist and {
                    'title': 'Support Record Timeline',
                    'kind': 'timeline',
                    'start': js_epoch(objlist.last().created),
                    'end': js_epoch(objlist.first().created + timedelta(hours=objlist.first().lost_time)),
                    'data': timeline_data,
                    'style': 'col-12'
                } or {}
            ]
        },
    ]}
    return stats


def feedback_stats(objlist, filters):
    feedback = objlist

    area_filters = {
        "{}{}".format(k.startswith('beamline') and 'feedback__session__' or 'feedback__', k): v
        for k, v in filters.items()
    }
    area_feedback = AreaFeedback.objects.filter(**area_filters)

    session_filters = {"{}".format('session__' in k and k.split('session__')[1] or k): v for k, v in filters.items()}
    sessions = Session.objects.filter(**session_filters)

    colors = ['#ffdd33', '#ffa333', '#66ffd5', '#00E6E2']
    period, year = ('year', None)
    field = "created__year"
    periods = sorted(objlist.values_list(field, flat=True).order_by(field).distinct())
    if len(periods) == 1:
        year = periods[0]
        sessions = sessions.filter(created__year=year)
        period = 'month'
        field = "created__month"
        periods = sorted(objlist.values_list(field, flat=True).order_by(field).distinct())
        if len(periods) == 1:
            year = "{} {}".format(calendar.month_name[periods[0]].title(), year)
            period = 'week'
            field = "created__week"
            periods = sorted(objlist.values_list(field, flat=True).order_by(field).distinct())
        else:
            periods = [i for i in range(1, 13)]
        field = "created__{}".format(period)

    period_dict = {per: period == 'month' and calendar.month_abbr[per].title() or per for per in periods}
    response_rate = [{
        period.title(): name,
        "Response Rate (%)": round(
            100. * sessions.filter(**{field: per}).filter(feedback__isnull=False).count() / max(1, sessions.filter(
                **{field: per}).count()), 2),
        "Sessions": sessions.filter(**{field: per}).count(),
        "Responses": sessions.filter(**{field: per}).filter(feedback__isnull=False).count()
    } for per, name in period_dict.items()]

    likerts = []
    areas_pk = SupportArea.objects.filter(user_feedback=True).values_list('scale__pk', flat=True)
    for scale in LikertScale.objects.filter(pk__in=areas_pk):
        choices = list(scale.choices())[:-1]
        choices = [choices[1], choices[0]] + choices[2:]
        choice_colors = dict(zip([c[1] for c in choices], colors))

        likert_data = [
            {
                **{'Area': area.name},
                **{
                    c[1]: area_feedback.filter(area=area, rating=c[0]).count() * (c[0] < 0 and -1 or 1)
                    for c in choices
                }
             } for area in SupportArea.objects.filter(user_feedback=True, scale=scale).order_by('pk')
        ]

        scale_feedback = area_feedback.exclude(rating=0).filter(area__scale=scale)
        likerts.append({
            'data': likert_data,
            'colors': choice_colors,
            'choices': choices,
            'average': scale_feedback and sum([a.rating for a in scale_feedback])/scale_feedback.count() or 0,
            'avgs': {
                e['Area']: sum([rating * abs(e[ch]) for rating, ch in choices]) / max(
                    sum([abs(e[ch]) for _, ch in choices]), 1)
                for e in likert_data
            }
        })

    stats = {'details': [
        {
            'title': 'User Experience',
            'description': 'Summary of impressions from user experience surveys',
            'style': "row",
            'content': [
                {
                   'title': 'User Experience Surveys',
                   'kind': 'barchart',
                   'data': {
                       'stack': [[c[1] for c in lt['choices']]],
                       'x-label': 'Area',
                       'aspect-ratio': 1,
                       'colors': lt['colors'],
                       'data': lt['data'],
                       "annotations": [
                           {"value": lt['average'], "text": "AVERAGE"}
                       ]
                   },
                   'notes': "<br>".join("<strong>{}</strong>: {:0.2f}".format(k, v) for k, v in lt['avgs'].items()) +
                            "<hr><strong>Overall Average:</strong> {:.2f}".format(lt['average']),
                   'style': 'col-12 col-md-6'
                } for lt in likerts
            ] + [
                {
                    'title': 'User Experience Survey Comments',
                    'notes': '<strong>User Feedback:</strong>\n\n' + linebreaksbr(
                        '\n\n'.join([c for c in feedback.values_list('comments', flat=True).distinct() if c])),
                    'style': 'col-12'
                },
                {
                    'title': 'Response Rate (%){}{}'.format(year and " in " or '', year or ''),
                    'kind': 'columnchart',
                    'data': {
                        'line': "Response Rate (%)",
                        'line-limits': [0, 100],
                        'x-label': period.title(),
                        'data': response_rate
                    },
                    'style': 'col-12'
                },
            ]
        },
    ]}
    return stats
