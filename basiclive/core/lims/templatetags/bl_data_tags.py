import collections
import json
import os

import numpy
import httpx2
from django import template
from django.urls import reverse

from basiclive.core.lims.conf import settings
from basiclive.utils import xdi

GOOG20_COLORS = [
    "#3366cc", "#dc3912", "#ff9900", "#109618", "#990099", "#0099c6", "#dd4477", "#66aa00", "#b82e2e",
    "#316395", "#994499", "#22aa99", "#aaaa11", "#6633cc", "#e67300", "#8b0707", "#651067", "#329262",
    "#5574a6", "#3b3eac"
]


register = template.Library()


@register.filter
def truncate_middle(value, max_length):
    """
    Truncates a string in the middle with an ellipsis if it exceeds max_length.
    Usage: {{ value|truncate_middle:20 }}
    """
    text = str(value)
    max_length = int(max_length)

    if len(text) <= max_length:
        return text

    # Account for the 1 character of the ellipsis (…)
    remaining_length = max_length - 1
    if remaining_length <= 0:
        return '…'

    # Split the remaining length between the start and the end
    front_len = remaining_length // 2
    back_len = remaining_length - front_len

    return f"{text[:front_len]}…{text[-back_len:]}"


@register.filter
def get_meta_data(data):
    return collections.OrderedDict(
        [(k, data.meta_data.get(k)) for k in data.kind.metadata if k in data.meta_data])


def get_json_info(path):
    url = settings.DOWNLOAD_PROXY_URL + reverse('files-proxy', kwargs={'section': 'raw', 'path': path})
    r = httpx2.get(url)
    if r.status_code == 200:
        return json.loads(r.content)
    else:
        print(f"File not found: {path}")
        return {}


def get_xdi_info(path):
    url = settings.DOWNLOAD_PROXY_URL + reverse('files-proxy', kwargs={'section': 'raw', 'path': path})
    r = httpx2.get(url)
    if r.status_code == 200:
        return xdi.read_xdi_data(r.content)
    else:
        print(f"File not found: {url}")
        return None


@register.simple_tag(takes_context=True)
def mad_report(context):
    data = context['data']
    if not data.url:
        return {}
    xdi_path = f'{data.url}/{data.file_name}'
    mad_path = f'{data.url}/{data.name}.xrf'
    raw = get_xdi_info(xdi_path)
    analysis = get_json_info(mad_path)

    if not (raw and analysis):
        return {}

    x_values = numpy.round(analysis["esf"]['energy'], 4).astype(float).tolist()
    exp_values = raw.data['normfluor'][:-1].astype(int).tolist()
    fp_values = numpy.round(analysis['esf']['fp'], 3).astype(float).tolist()
    fpp_values = numpy.round(analysis['esf']['fpp'], 3).astype(float).tolist()
    x_label = 'Energy ({})'.format(raw['column.1'].units)

    choices = [
        dict((str(k), isinstance(v, str) and str(v) or v) for k, v in choice.items())
                for choice in analysis['choices']
    ]

    report = {'details': [
        {
            'title': '',
            'style': "row",
            'content': [
                {
                    'title': 'MAD Scan',
                    'kind': 'lineplot',
                    'data':
                        {
                            'x': [x_label] + x_values,
                            'y1': [
                                ['Experiment'] + exp_values,
                            ],
                            'y2': [
                                ['f`'] + fp_values,
                                ['f``'] + fpp_values,
                            ],
                            'x-label': x_label,
                            'y1-label': 'Fluorescence',
                            'y2-label': 'Anomalous Scattering Factors',
                            'aspect-ratio': 1.5,
                            'annotations': [
                                {'value': choice['energy'], 'text': choice['label'].upper()}
                                for choice in choices
                            ]
                        },
                    'id': 'mad',
                    'style': 'col-12',
                },
            ]
        },
    ]}

    return {
        'report': report,
        'choices': choices
    }


def summarize_assignments(edges, precision=3):
    """
    Takes an XRF assignment and summarizes it for display purposes, combining close edges

    :param edges: list of tuples representing (label, energy, abundance) for each assigned edge
    :param precision: floating point precision for comparing energy values, default 3.
    :return: A list of dictionaries like {'label': ..., 'energy': ..., 'amplitude': ...}
    """

    edge_names = collections.defaultdict(list)
    edge_amplitudes = collections.defaultdict(int)

    for name, energy, amplitude in edges:
        key = (round(energy, precision),)
        edge_names[key].append(name)
        edge_amplitudes[key] += amplitude

    return [
        {
            'label': os.path.commonprefix(names),
            'energy': key[0],
            'amplitude': edge_amplitudes[key],
        }
        for key, names in edge_names.items()
    ]


@register.simple_tag(takes_context=True)
def xrf_report(context):
    data = context['data']
    if not data.url:
        return {}
    xdi_path = f'{data.url}/{data.file_name}'
    xrf_path = f'{data.url}/{data.name}.xrf'
    raw = get_xdi_info(xdi_path)
    analysis = get_json_info(xrf_path)

    if not raw:
        return {}

    if analysis:
        assignments = [
            {
                'label': el,
                'reliability': round(values[0], 3),
                'edges': summarize_assignments(values[1], precision=1)
            } for el, values in analysis.get('assignments', {}).items()
        ]
        assignments.sort(key=lambda x: -x['reliability'])
        for i in range(len(assignments)):
            assignments[i]['color'] = GOOG20_COLORS[i % 20]
    else:
        assignments = []

    valid = (raw.data['energy'] > 0.25) & (raw.data['energy'] < data.energy)
    ymax = numpy.ceil(raw.data['normfluor'][valid].max() * 1.05)
    x_values = numpy.round(analysis.get('energy', []), 3).astype(float).tolist()
    exp_values = raw.data['normfluor'].astype(int).tolist()
    fit_values = numpy.round(analysis.get('fit', [])).astype(int).tolist()
    x_label = 'Energy ({})'.format(raw['column.1'].units)

    report = {'details': [
        {
            'title': '',
            'style': "row",
            'content': [
                {
                    'title': 'XRF Spectrum, select elements on the right to show/hide emission lines',
                    'kind': 'lineplot',
                    'data':
                        {
                            'x': [x_label] + x_values,
                            'y1': [
                                ['Experiment'] + exp_values,
                                ['Fit'] + fit_values,
                            ],
                            'aspect-ratio': 1.5,
                            'y1-label': 'Fluorescence',
                            'y1-limits': [0, int(ymax)],
                            'x-limits': [0.25, float(data.energy)],
                        },
                    'id': 'xrf',
                    'style': 'col-12',
                },
            ]
        },
    ]}

    return {
        'report': report,
        'assignments': assignments
    }