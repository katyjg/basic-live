# Generated migration to add phone field to User and populate from Project contact_phone

from django.db import migrations, models
from django.db.models import Q

from basiclive.core.lims.models import Project


def populate_user_phone_from_projects(apps, schema_editor):
    User = apps.get_model('lims', 'User')
    Project = apps.get_model('lims', 'Project')

    for user in User.objects.all():
        # Check project where user is PI
        project = (
            Project.objects.filter(Q(pi_id=user.pk) | Q(memberships__user_id=user.pk))
            .order_by('-modified')
            .first()
        )
        modified = []
        if project:
            user.default_project = project
            modified.append('default_project')
            if project.contact_phone:
                user.phone = project.contact_phone
                modified.append('phone')
            user.save(update_fields=modified)


def reverse_populate_user_phone(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0112_alter_data_session'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='phone',
            field=models.CharField(blank=True, default='', max_length=60, verbose_name='Phone'),
        ),
        migrations.RunPython(
            populate_user_phone_from_projects,
            reverse_code=reverse_populate_user_phone,
        ),
    ]
