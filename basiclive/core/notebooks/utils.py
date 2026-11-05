from datetime import timedelta
from decimal import Decimal
from functools import partial
from itertools import tee
import json

from django.db.models import Q
from django.utils import timezone


def timeish(dt):
    """
    Format date time in a short human friendly manner
    :param dt: datetime object
    :return: formatted string
    """
    now = timezone.now()
    elapsed = now - dt
    seconds = int(elapsed.total_seconds())
    minutes = seconds / 60
    hours = minutes / 60
    if elapsed < timedelta(minutes=1):
        txt = 'now'
    elif elapsed < timedelta(hours=1):
        txt = f'{minutes:0.0f}min'
    elif elapsed < timedelta(days=1):
        txt = f'{hours:0.0f}h'
    elif elapsed < timedelta(weeks=52):
        txt = f'{dt.strftime("%b")} {dt.day}'
    else:
        txt = f'{dt.day} {dt.strftime("%b")} {dt.year}'
    return txt


def simpletime(dt):
    """
    Format date time in a short human friendly manner
    :param dt: datetime object
    :return: formatted string
    """
    tztime = timezone.localtime(dt)
    now = timezone.now()
    elapsed = now - dt
    seconds = int(elapsed.total_seconds())
    minutes = seconds / 60
    hours = minutes / 60
    if elapsed < timedelta(days=1):
        txt = tztime.strftime('%H:%M %Z')
    elif elapsed < timedelta(weeks=52):
        txt = tztime.strftime('%b %d, %H:%M %Z')
    else:
        txt = tztime.strftime('%b %d %Y, %H:%M %Z')
    return txt


FUZZY_OPERATORS = [">", "<", "<=", ">=", "="]
FUZZY_UNITS = ["hour", "day", "week", "month", "year"]
FUZZY_MAX = [24, 7, 4, 12, 0]


def fuzzy_time(spec, field='created'):
    """
    Generate a datetime query based on a fuzzy date string
    :param spec: human friendly text representing date
    :param field: field to use for query
    :return: Q() object for the corresponding query or a dummy Q object if parsing is unsuccessful

    Examples: "< 3 weeks", "> 4 days", "> 5 years", ...
    """
    tokens = spec.split()
    now = timezone.now()
    query = {f'{field}__gt': now}

    if len(tokens) != 3:
        return Q(**query)
    operator, quantity, unit = tokens

    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        return Q()

    unit = unit if unit.endswith("s") else unit + "s"
    if unit == "months":
        unit = "days"
        quantity *= 30
    elif unit == "years":
        unit = "weeks"
        quantity *= 52

    if operator == "<":
        query = {f"{field}__gt": now - timedelta(**{unit: max(quantity - 1, 0.1)})}
    elif operator == "<=":
        query = {f"{field}__gt": now - timedelta(**{unit: quantity})}
    elif operator == ">":
        query = {f"{field}__lt": now - timedelta(**{unit: quantity + 1})}
    elif operator == ">=":
        query = {f"{field}__lt": now - timedelta(**{unit: quantity})}
    elif operator == "=":
        query = {
            f"{field}__lt": now - timedelta(**{unit: max(quantity - 1, 0.1)}),
            f"{field}__gte": now - timedelta(**{unit: quantity})
        }
    return Q(**query)


def pairwise(column):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = tee(filter(lambda v: isinstance(v, (float, int)), column))
    next(b, None)
    return zip(a, b)


class Converter:
    def __init__(self, prec):
        self.prec = prec
        if self.prec == 0:
            self.converter = lambda x: x
        else:
            self.converter = partial(round, ndigits=prec + 1)

    def __call__(self, val):
        if isinstance(val, (float, int)):
            return self.converter(val)
        return val


def float_cast(item):
    try:
        return float(item)
    except ValueError:
        return item


def clean_json(text):
    """
    Clean JSON text to adjust precision of floating point values
    :param text: json text
    :return: cleaned json text
    """
    data = json.loads(text)
    if 'data' in data and isinstance(data['data'], dict):
        for key, col in data['data'].items():
            try:
                minv = min(pairwise(sorted(col)), key=lambda x: x[1] - x[0])
                prec = abs(Decimal('{:.1g}'.format(minv[1] - minv[0])).as_tuple().exponent)
            except (ValueError, TypeError):
                prec = 0
            conv = Converter(prec)
            data['data'][key] = [conv(v) for v in col]
    return json.dumps(data, separators=(',', ':'))
