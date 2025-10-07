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


def make_table(data, columns: list, rows: list, total_col=True, total_row=True, strings=False):
    """
    Converts a list of dictionaries into a list of lists ready for displaying as a table
    :param data: list of dictionaries (one dictionary per column header)
    :param columns: list of column headers to display in table, ordered the same as data
    :param rows: list of row headers to display in table
    :param total_col: include a total column
    :param total_row: include a total row
    :param strings: convert all cells to strings
    :return: list of lists
    """

    import pprint
    pprint.pprint(data)

    headers = [''] + columns
    table_data = [headers] + [
        [key] + [item.get(key, 0) for item in data]
        for key in rows
    ]

    if total_row:
        table_data.append(
            ['Total'] + [
                sum([row[i] for row in table_data[1:]])
                for i in range(1, len(headers))
            ]
        )

    if total_col:
        table_data[0].append('All')
        for row in table_data[1:]:
            row.append(sum(row[1:]))

    if strings:
        table_data = [
            [f'{item}' for item in row]
            for row in table_data
        ]

    return table_data
