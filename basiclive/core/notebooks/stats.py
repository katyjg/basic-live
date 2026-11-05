"""Statistics and metrics reporting for basiclive.core.notebooks."""

from django.db.models import Count, Q

from .models import Annotation, Entry, EntryType, Notebook


def notebook_metrics(user=None):
    """
    Compute aggregate metrics for notebooks, entries, active days, and annotations.
    If user is specified, metrics are calculated for notebooks accessible by that user.
    """
    if user and not getattr(user, 'is_authenticated', False):
        notebook_qs = Notebook.objects.none()
    elif user and not (getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)):
        notebook_qs = Notebook.objects.none()
    else:
        notebook_qs = Notebook.objects.all()

    total_notebooks = notebook_qs.count()
    entries_qs = Entry.objects.filter(notebook__in=notebook_qs)
    total_entries = entries_qs.count()
    total_days = entries_qs.dates('created', 'day').count()

    annotations_qs = Annotation.objects.filter(entry__in=entries_qs)
    total_annotations = annotations_qs.count()

    kind_counts = dict(
        entries_qs.values_list('kind__name')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    return {
        'total_notebooks': total_notebooks,
        'total_days': total_days,
        'total_entries': total_entries,
        'total_annotations': total_annotations,
        'entries_by_kind': kind_counts,
    }


def project_notebook_metrics(project):
    """
    Compute notebook metrics scoped to a specific project.
    """
    if project and hasattr(project, 'members'):
        member_ids = list(project.members.values_list('pk', flat=True))
        if getattr(project, 'pi_id', None):
            member_ids.append(project.pi_id)
        entries_qs = Entry.objects.filter(author_id__in=member_ids)
    elif project and hasattr(project, 'pk'):
        entries_qs = Entry.objects.filter(author_id=project.pk)
    else:
        entries_qs = Entry.objects.none()

    notebook_ids = entries_qs.values_list('notebook_id', flat=True).distinct()
    total_days = entries_qs.dates('created', 'day').count()

    return {
        'total_notebooks': notebook_ids.count(),
        'total_days': total_days,
        'total_entries': entries_qs.count(),
        'entries_by_kind': dict(
            entries_qs.values_list('kind__name')
            .annotate(total=Count('id'))
            .order_by('-total')
        ),
    }
