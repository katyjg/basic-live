import abc
import calendar
import datetime
from datetime import timedelta
from typing import Literal

from django.contrib import admin
from django.db.models import Min, ExpressionWrapper, F, fields, Func
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class FilterFactory(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def new(cls, *args, **kwargs) -> admin.SimpleListFilter:
        ...


class YearLimitFilterFactory(FilterFactory):

    @classmethod
    def new(
            cls, field_name='created', filter_type: Literal['before', 'after', 'since', 'until'] = 'after',
            filter_title=None
    ):
        filter_title = filter_title if filter_title else f"{field_name.replace('_', ' ').title()} {filter_type.title()}"

        class YearLimitListFilter(admin.SimpleListFilter):
            title = filter_title
            parameter_name = f'{field_name}_{filter_type}'
            lookup_opr = {
                'since': '__gte',
                'until': '__lte',
                'before': '__lt',
                'after': '__gt'
            }.get(filter_type)

            def __init__(self, request, new_params, model, *args, **kwargs):
                self.model = model
                super().__init__(request, new_params, model, *args, **kwargs)

            def lookups(self, request, model_admin):
                qs = self.model.objects.filter()
                value_field = f'{field_name}__year'
                choices = qs.values_list(value_field, flat=True).order_by(value_field).distinct()
                return ((yr, f'{yr}') for yr in choices)

            def queryset(self, request, queryset):
                try:
                    value = int(self.value())
                    flt = {f'{field_name}__year{self.lookup_opr}': value}
                except (ValueError, TypeError):
                    flt = {}
                return queryset.filter(**flt)

        return YearLimitListFilter


class YearFilterFactory(FilterFactory):

    @classmethod
    def new(cls, field_name='created', start=None, end=None, reverse=True):
        end = end if end else timezone.now().year
        start = start if start else end - 15

        class YearListFilter(admin.SimpleListFilter):
            parameter_name = f'{field_name}_year'
            title = parameter_name.replace('_', ' ').title()

            def lookups(self, request, model_admin):
                choices = range(start, end + 1) if not reverse else reversed(range(start, end + 1))
                return ((yr, f'{yr}') for yr in choices)

            def queryset(self, request, queryset):
                flt = {} if not self.value() else {f'{field_name}__year': self.value()}
                return queryset.filter(**flt)

        return YearListFilter


class MonthFilterFactory(FilterFactory):
    @classmethod
    def new(cls, field_name='created'):
        class MonthFilter(admin.SimpleListFilter):
            parameter_name = f'{field_name}_month'
            title = parameter_name.replace('_', ' ').title()

            def lookups(self, request, model_admin):
                return ((month, calendar.month_name[month]) for month in range(1, 13))

            def queryset(self, request, queryset):
                flt = {} if not self.value() else {f'{field_name}__month': self.value()}
                return queryset.filter(**flt)

        return MonthFilter


class QuarterFilterFactory(FilterFactory):
    @classmethod
    def new(cls, field_name='created'):
        class QuarterFilter(admin.SimpleListFilter):
            parameter_name = f'{field_name}_quarter'
            title = parameter_name.replace('_', ' ').title()

            def lookups(self, request, model_admin):
                return ((i + 1, f'Q{i + 1}') for i in range(4))

            def queryset(self, request, queryset):
                flt = {} if not self.value() else {f'{field_name}__quarter': self.value()}
                return queryset.filter(**flt)

        return QuarterFilter


class TimeScaleFilterFactory(FilterFactory):
    @classmethod
    def new(cls):
        class TimeScaleFilter(admin.SimpleListFilter):
            parameter_name = 'time_scale'
            title = parameter_name.replace('_', ' ').title()

            def lookups(self, request, model_admin):
                return (
                    ('month', 'Month'),
                    ('quarter', 'Quarter'),
                    ('cycle', 'Cycle'),
                    ('year', 'Year')
                )

            def queryset(self, request, queryset):
                flt = {}
                return queryset.filter(**flt)

        return TimeScaleFilter


class FutureDateListFilterFactory(FilterFactory):
    @classmethod
    def new(cls, field_name='due_date'):
        class FutureDateListFilter(admin.SimpleListFilter):
            parameter_name = f'{field_name}_due'
            title = field_name.title().replace('_', ' ')

            def lookups(self, request, model_admin):
                return [
                    ('expired', _('Expired')), ('today', _('Today')), ('tomorrow', _('Tomorrow')),
                    ('7days', _('Within 7 days')), ('month', _('This month')), ('year', _('This year')),
                ]

            def queryset(self, request, queryset):
                now = timezone.now()
                # When time zone support is enabled, convert "now" to the user's time
                # zone so Django's definition of "Today" matches what the user expects.
                if timezone.is_aware(now):
                    now = timezone.localtime(now)

                today = now.date()
                tomorrow = today + datetime.timedelta(days=1)
                if today.month == 12:
                    next_month = today.replace(year=today.year + 1, month=1, day=1)
                else:
                    next_month = today.replace(month=today.month + 1, day=1)
                next_year = today.replace(year=today.year + 1, month=1, day=1)

                kwarg_since = f'{field_name}__gte'
                kwarg_until = f'{field_name}__lt'

                if not self.value():
                    query = {}
                elif self.value() == 'expired':
                    query = {kwarg_until: today}
                elif self.value() == 'today':
                    query = {field_name: tomorrow}
                elif self.value() == 'tomorrow':
                    query = {field_name: today}
                elif self.value() == '7days':
                    query = {kwarg_since: today, kwarg_until: today + datetime.timedelta(days=7)}
                elif self.value() == 'month':
                    query = {kwarg_since: today, kwarg_until: next_month}
                elif self.value() == 'year':
                    query = {kwarg_since: today, kwarg_until: next_year}
                else:
                    query = {}
                return queryset.filter(**query)

        return FutureDateListFilter


class NewEntryFilterFactory(FilterFactory):

    @classmethod
    def new(cls, field_label='New Entry', field_name='created', distinct='project__sessions'):
        class NewEntryFilter(admin.SimpleListFilter):
            parameter_name = f'{field_label}'
            title = parameter_name.replace('_', ' ').title()

            def lookups(self, request, model_admin):
                return ((1, f'{field_label}'),)

            def queryset(self, request, queryset):
                if not self.value():
                    flt = {}
                else:
                    max = ExpressionWrapper(
                        F(field_name) - Min(
                            f'{distinct}__{field_name}'
                        ), output_field=fields.DurationField()
                        )
                    queryset = queryset.annotate(max_time=max)
                    flt = {'max_time': timedelta(hours=0)}
                return queryset.filter(**flt)

        return NewEntryFilter


class TagFilterFactory(FilterFactory):
    @classmethod
    def new(cls, field_name='tags'):
        class TagFilter(admin.SimpleListFilter):
            parameter_name = f'{field_name}'
            title = parameter_name.replace('_', ' ').title()

            def __init__(self, request, new_params, model, *args, **kwargs):
                self.model = model
                super().__init__(request, new_params, model, *args, **kwargs)

            def lookups(self, request, model_admin):
                try:
                    tag_list = self.model.objects.annotate(
                        unpacked_tags=Func('tags', function='jsonb_array_elements_text')
                    ).values_list('unpacked_tags', flat=True).order_by('unpacked_tags').distinct()
                    return ((tag, tag) for tag in tag_list if tag)
                except Exception:
                    tags = set()
                    for t_list in self.model.objects.values_list(field_name, flat=True):
                        if isinstance(t_list, list):
                            tags.update(t_list)
                    return ((tag, tag) for tag in sorted(tags) if tag)

            def queryset(self, request, queryset):
                if not self.value():
                    return queryset
                from django.db import connection
                if connection.vendor == 'postgresql':
                    return queryset.filter(**{f'{field_name}__contains': [self.value()]})
                else:
                    return queryset.filter(**{f'{field_name}__icontains': self.value()})

        return TagFilter


def TagFilter(*args, **kwargs):
    return TagFilterFactory.new(*args, **kwargs)


def DateLimitFilter(*args, **kwargs):
    return YearLimitFilterFactory.new(*args, **kwargs)


def StartYearFilter(field_name, filter_title='Start Year'):
    return YearLimitFilterFactory.new(field_name=field_name, filter_title=filter_title, filter_type='since')


def EndYearFilter(field_name, filter_title='End Year'):
    return YearLimitFilterFactory.new(field_name=field_name, filter_title=filter_title, filter_type='until')


def YearFilter(*args, **kwargs):
    return YearFilterFactory.new(*args, **kwargs)


def MonthFilter(*args, **kwargs):
    return MonthFilterFactory.new(*args, **kwargs)


def QuarterFilter(*args, **kwargs):
    return QuarterFilterFactory.new(*args, **kwargs)


def FutureDateFilter(*args, **kwargs):
    return FutureDateListFilterFactory.new(*args, **kwargs)


def TimeScaleFilter(*args, **kwargs):
    return TimeScaleFilterFactory.new(*args, **kwargs)


def NewEntryFilter(*args, **kwargs):
    return NewEntryFilterFactory.new(*args, **kwargs)
