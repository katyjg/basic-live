import calendar
import logging
from datetime import datetime, time, timedelta

from django import template
from django.utils import timezone

from basiclive.core.schedule.conf import settings
from basiclive.core.schedule.models import BeamlineSupport, FacilityMode
from basiclive.core.schedule.providers import get_schedule_provider

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
    dates = month[i * 7:i * 7 + 7]
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

    provider = get_schedule_provider()
    if provider is not None:
        provider.sync(start, end)

    start_dt = timezone.make_aware(datetime.combine(start, time.min))
    end_dt = timezone.make_aware(datetime.combine(end, time.min))
    intervals = (
        FacilityMode.objects.filter(end__gt=start_dt, start__lt=end_dt)
        .select_related("mode")
        .order_by("start")
    )
    for interval in intervals:
        if not interval.start or not interval.end:
            continue
        st = max(timezone.localtime(interval.start), start_dt)
        en = min(timezone.localtime(interval.end), end_dt)
        while st < en:
            dt = format_local_date(st)
            hr = format_local_hour(st)
            st += timedelta(hours=slot)
            if dt in info['week'] and hr in info['week'][dt]['modes']:
                info['week'][dt]['modes'][hr] = {
                    'kind': interval.mode.code,
                    'css_class': interval.mode.css_class,
                    'description': interval.mode.description,
                }

    return info
