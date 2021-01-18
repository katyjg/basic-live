from datetime import timedelta


def humanize_duration(duration, sec=False):
    if isinstance(duration, (int, float)):
        return natural_seconds(timedelta(hours=duration).total_seconds())
    return natural_seconds(duration.total_seconds())


def natural_seconds(seconds, depth=2):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    weeks, days = divmod(days, 7)
    months, weeks = divmod(weeks, 4.35)
    years, months = divmod(months, 12)

    units = ['year', 'month', 'week', 'day', 'hour', 'min', 'sec']
    values = [years, months, weeks, days, hours, minutes, seconds]
    entries = [
        '{:0.0f} {}{}'.format(val, unit, 's' if val > 1 else '')
        for val, unit in zip(values, units) if round(val) > 0
    ]

    return ' '.join(entries[:depth]) or '0 minutes'


def natural_duration(delta):
    return natural_seconds(delta.total_seconds())