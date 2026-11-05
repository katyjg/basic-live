# Generated data migration to migrate Project auth data to User and ProjectMembership

from django.db import migrations
from django.utils import timezone

from basiclive.core.lims.models import Project


def migrate_project_data_to_users(apps, schema_editor):
    Project = apps.get_model('lims', 'Project')
    User = apps.get_model('lims', 'User')
    ProjectMembership = apps.get_model('lims', 'ProjectMembership')
    SSHKey = apps.get_model('lims', 'SSHKey')
    SupportRecord = apps.get_model('crm', 'SupportRecord')
    BeamlineSupport = apps.get_model('schedule', 'BeamlineSupport')
    Entry = apps.get_model('notebooks', 'Entry')
    Annotation = apps.get_model('notebooks', 'Annotation')

    for project in Project.objects.all().order_by('pk'):
        username = getattr(project, 'username', None) or getattr(project, 'name', None)
        if not username:
            continue

        # Get or create corresponding User account
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={
                'first_name': getattr(project, 'first_name', '') or '',
                'last_name': getattr(project, 'last_name', '') or '',
                'email': getattr(project, 'email', '') or getattr(project, 'contact_email', '') or '',
                'name': getattr(project, 'name', '') or '',
                'password': getattr(project, 'password', '') or '',
                'is_active': getattr(project, 'is_active', True),
                'is_staff': getattr(project, 'is_staff', False),
                'is_superuser': getattr(project, 'is_superuser', False),
                'date_joined': getattr(project, 'date_joined', None) or timezone.now(),
                'last_login': getattr(project, 'last_login', None),
            }
        )

        # Set project PI
        if not project.pi_id:
            project.pi = user
            project.save(update_fields=['pi'])

        # Create PI ProjectMembership
        ProjectMembership.objects.get_or_create(
            user=user,
            project=project,
            defaults={'role': 'PI'}
        )

        # Re-link SSHKeys
        SSHKey.objects.filter(project=project).update(user_id=user.pk)

        # Migrate SupportRecord staff if pointing to this project
        SupportRecord.objects.filter(staff_id=project.pk).update(user_id=user.pk)

        # Migrate BeamlineSupport staff
        BeamlineSupport.objects.filter(staff_id=project.pk).update(user_id=user.pk)

        # Migrate Notebook authors
        Entry.objects.filter(author_id=project.pk).update(_author_id=user.pk)
        Annotation.objects.filter(author_id=project.pk).update(_author_id=user.pk)

    # Clean up any dangling IDs before constraints are added
    valid_user_ids = set(User.objects.values_list('pk', flat=True))
    SupportRecord.objects.exclude(user_id__in=valid_user_ids).update(user_id=None)
    SSHKey.objects.exclude(user_id__in=valid_user_ids).update(user_id=None)
    BeamlineSupport.objects.exclude(user_id__in=valid_user_ids).delete()


def reverse_migrate_project_data_to_users(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0103_add_user_and_membership'),
        ('crm', '0082_alter_supportrecord_staff'),
        ('schedule', '0006_alter_beamtime_project'),
        ('notebooks', '0004_remove_notebook_access_remove_notebook_editor_and_more'),
    ]

    operations = [
        migrations.RunPython(
            migrate_project_data_to_users,
            reverse_code=reverse_migrate_project_data_to_users,
        ),
    ]
