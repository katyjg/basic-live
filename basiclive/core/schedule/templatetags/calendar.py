from django import template
from django.conf import settings
from django.utils import timezone

from basiclive.core.schedule.models import BeamlineSupport

from datetime import datetime, date, timedelta, time
import pytz
import calendar
import requests

import warnings

import logging
logger = logging.getLogger(__name__)

register = template.Library()


def format_localtime(dt):
    return datetime.strftime(timezone.localtime(pytz.utc.localize(dt)), '%Y-%m-%dT%H')


def format_localdate(dt):
    return datetime.strftime(timezone.localtime(pytz.utc.localize(dt)), '%Y-%m-%d')


def format_localhour(dt):
    return datetime.strftime(timezone.localtime(pytz.utc.localize(dt)), '%H')


@register.simple_tag
def calendar_view(year, week):
    d = datetime.strptime("{}-W{}".format(year, week) + '-1', '%G-W%V-%w')
    cal = calendar.Calendar(calendar.MONDAY)
    month = list(cal.itermonthdates(d.year, d.month))
    i = [m.isocalendar()[1] for m in month[0::7]].index(d.isocalendar()[1])

    slot = settings.HOURS_PER_SHIFT
    shift_count = int(24 / slot)
    shifts = {'{:02d}'.format(i * slot): {} for i in range(shift_count)}

    names = [calendar.day_abbr[x] for x in cal.iterweekdays()]
    dates = month[i*7:i*7+7]
    start = dates[0]
    end = dates[-1] + timedelta(days=1)
    info = {
        'week': {
            datetime.strftime(d, '%Y-%m-%d'): {
                'name': nm,
                'date': d,
                'modes': shifts.copy(),
                'support': BeamlineSupport.objects.filter(date=d).first() }
            for nm, d in zip(names, dates)
        },
        'shifts': shift_count,
        'start': datetime.strftime(start, '%Y-%m-%d'),
        'end': datetime.strftime(end, '%Y-%m-%d'),
    }

    """Could be moved to AJAX request if Access-Control-Allow-Origin header added to api resource"""

    if getattr(settings, "FACILITY_MODES", False):
        try:
            url = "{}?start={}&end={}".format(settings.FACILITY_MODES, start, end)
            r = requests.get(url)
            if r.status_code == 200:
                for mode in r.json():
                    st = datetime.strptime(mode['start'], '%Y-%m-%dT%H:%M:%SZ')
                    while st < datetime.strptime(mode['end'], '%Y-%m-%dT%H:%M:%SZ'):
                        dt = format_localdate(st)
                        hr = format_localhour(st)
                        st += timedelta(hours=slot)
                        if dt in info['week'].keys():
                            info['week'][dt]['modes'][hr] = {
                                'kind': str(mode['kind'])
                            }
        except requests.exceptions.ConnectionError:
            warnings.warn("Couldn't fetch beam modes from {}.".format(settings.FACILITY_MODES))
        except requests.exceptions.MissingSchema:
            warnings.warn("FACILITY_MODE must start with 'http://' or 'https://'.")

    return info


