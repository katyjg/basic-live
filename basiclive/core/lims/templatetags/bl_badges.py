from django import template
from basiclive.utils import colors

register = template.Library()


@register.filter("dataset")
def dataset(data):
    if data.kind.acronym in ['RASTER', 'SCREEN', 'XRD', 'DATA']:
        return f"{len(data.frames)} imgs"
    else:
        return f"{data.energy} keV"


@register.filter("report_summary")
def report_summary(report):
    return f"{report.score:0.2f}"


@register.inclusion_tag('lims/components/badge-score.html')
def score_badge(score):
    rgba = colors.colormap(score)
    r, g, b, a = rgba
    return {
        'score': round(score, 2),
        'styles': (
            f"background-color: rgba({r}, {g}, {b}, {a:0.2f});"
            f"color: contrast-color(rgba({r}, {g}, {b}, {a:0.2f}));"
        )
    }


@register.inclusion_tag('lims/components/badge-label.html')
def label_badge(header="", classes="", value=0, score=None):
    if score is not None:
        rgba = colors.colormap(score)
        r, g, b, a = rgba
        styles = (
            "font-weight: 600;"
            f"background-color: rgba({r}, {g}, {b}, {a:0.2f});"
            f"color: contrast-color(rgba({r}, {g}, {b}, {a:0.2f}));"
        )
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
