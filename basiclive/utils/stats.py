from django.db.models import Count

import calendar
import numpy


def get_histogram_points(data, range=None, bins='doane'):
    counts, edges = numpy.histogram(data, bins=bins, range=range)
    centers = (edges[:-1] + edges[1:]) * 0.5
    return list(zip(centers, counts))


def generic_stats(objlist, fields, date_field=None):
    stats = {}
    if objlist:
        model = objlist.first()._meta.verbose_name_plural
        content = []
        data = {}
        options = {}
        period, year = (None, None)

        for fld in fields:
            kind = fields.get(fld, {}).get('kind', 'columnchart')
            if kind == 'pie':
                data[fld] = {
                    'data': [
                        {
                            'label': (isinstance(d[fld], int) or isinstance(d[fld], float)) and str(int(d[fld])) or str(d[fld]),
                            'value': d['count'],
                        } for d in objlist.filter(**{'{}__isnull'.format(fld): False}).values(fld).order_by(fld).annotate(count=Count('id'))
                    ]
                }
            elif kind == 'histogram':
                histo = get_histogram_points(
                    [ float(datum[fld]) for datum in objlist.values(fld) if datum[fld] is not None ],
                    range=fields.get(fld, {}).get('range'), bins=fields.get(fld, {}).get('bins', 'doane')
                )
                data[fld] = {
                    'data': [
                        {"x": row[0], "y": row[1]} for row in histo
                    ],
                }
            elif kind == 'columnchart':
                if date_field:
                    period = 'year'
                    field = "{}__{}".format(date_field, period)
                    periods = sorted(objlist.values_list(field, flat=True).order_by(field).distinct())
                    if len(periods) == 1:
                        year = periods[0]
                        period = 'month'
                        periods = [i for i in range(1, 13)]
                        field = "{}__{}".format(date_field, period)
                    period_dict = {per: period == 'year' and per or calendar.month_abbr[per].title() for per in periods}
                    period_data = [
                            {
                                **{period.title(): period_dict[per]},
                                **{str(k[fld]): k['count']
                                   for k in
                                   objlist.filter(**{field: per}).values(fld).order_by(fld).annotate(count=Count('id'))}
                            } for per in periods
                        ]
                    options[fld] = set([k for p in period_data for k in p.keys()]).difference([period.title()])
                    data[fld] = {
                        'aspect-ratio': 2,
                        'stack': [list(options[fld])],
                        'x-label': period and period.title() or fld.replace('__', ' ').title(),
                        'data': period_data
                    }
                    for opt in options[fld]:
                        for e in data[fld]['data']:
                            e[opt] = e.get(opt, 0)
                else:
                    field_data = [
                        {
                            fld.replace('__', ' ').title(): str(datum[fld]),
                            "Count": datum['count'],
                        } for datum in objlist.values(fld).order_by(fld).annotate(count=Count('id'))
                    ]
                    data[fld] = {
                        'aspect-ratio': 2,
                        'stack': [list(set([k for p in field_data for k in p.keys()]))],
                        'x-label': period and period.title() or fld.replace('__', ' ').title(),
                        'data': field_data
                    }

            plot = {
                'title': "{} by {}".format(model.title(), fld.replace('__', ' ').title()),
                'kind': kind,
                'data': data.get(fld, {}),
                'style': 'col-12 col-md-6'
            }
            content.append(plot)
        stats = {
            'details': [
                {
                    'title': '{}{}{}'.format(model.title(), year and ' in ' or '', year or ''),
                    'style': "row",
                    'content': content
                }
            ]
        }
    return stats
