import calendar
import isodate
import logging
import warnings
from datetime import datetime, timedelta

import pytz
import requests
from basiclive.core.schedule.models import BeamlineSupport
from django import template
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

register = template.Library()


def format_local_time(dt):
    return timezone.localtime(dt).strftime('%Y-%m-%dT%H')


def format_local_date(dt):
    return timezone.localtime(dt).strftime('%Y-%m-%d')


def format_local_hour(dt):
    return timezone.localtime(dt).strftime('%H')


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
            d.strftime('%Y-%m-%d'): {
                'name': nm,
                'date': d,
                'modes': shifts.copy(),
                'support': BeamlineSupport.objects.filter(date=d).first()
            }
            for nm, d in zip(names, dates)
        },
        'shifts': shift_count,
        'start': start.strftime('%Y-%m-%d'),
        'end': end.strftime('%Y-%m-%d'),
    }

    # Could be moved to AJAX request if Access-Control-Allow-Origin header added to api resource
    if getattr(settings, "FACILITY_MODES", False):
        try:
            url = f"{settings.FACILITY_MODES}?start={start}&end={end}"
            r = requests.get(url)
            if r.status_code == 200:
                for mode in r.json():
                    st = isodate.parse_datetime(mode['start'])
                    en = isodate.parse_datetime(mode['end'])
                    while st < en:
                        dt = format_local_date(st)
                        hr = format_local_hour(st)
                        st += timedelta(hours=slot)
                        if dt in info['week'].keys():
                            info['week'][dt]['modes'][hr] = {
                                'kind': str(mode['kind'])
                            }
        except requests.exceptions.ConnectionError:
            warnings.warn(f"Couldn't fetch beam modes from {settings.FACILITY_MODES}.")
        except requests.exceptions.MissingSchema:
            warnings.warn("FACILITY_MODE must start with 'http://' or 'https://'.")

    return info


