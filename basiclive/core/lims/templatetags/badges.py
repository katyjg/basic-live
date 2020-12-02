from django import template
from basiclive.utils import colors

register = template.Library()


@register.filter("dataset")
def dataset(data):
    if data.kind.acronym in ['RASTER', 'SCREEN', 'XRD', 'DATA']:
        return "{} imgs".format(len(data.frames))
    else:
        return "{} keV".format(data.energy)


@register.filter("report_summary")
def report_summary(report):
    return "{:0.2f}".format(report.score)


@register.inclusion_tag('lims/components/badge-score.html')
def score_badge(score):
    rgba = colors.colormap(score)
    return {
        'score': round(score, 2),
        'styles': (
            "text-shadow: 0 0 2px rgba(0, 0, 0, 0.9); "
            "color: #fff; "
            "background-color: rgba({}, {}, {}, {:0.2f});"
        ).format(*rgba)
    }


@register.inclusion_tag('lims/components/badge-label.html')
def label_badge(header="", classes="", value=0, score=None):
    if score is not None:
        rgba = colors.colormap(score)
        styles = (
            "text-shadow: 0 0 2px rgba(0, 0, 0, 0.9); "
            "color: #fff; font-weight: 600;"
            "background-color: rgba({}, {}, {}, {:0.2f});"
        ).format(*rgba)
    else:
        styles = ""
    return {
        'header': header,
        'classes': classes,
        'styles': styles,
        'value': value
    }


@register.filter("score_color")
def score_color(value):
    rgba = colors.colormap(value)
    return 'rgba({}, {}, {}, {:0.2f})'.format(*rgba)
