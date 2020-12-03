# Generated by Django 3.0.1 on 2019-12-31 22:33

from django.db import migrations, models
import django.utils.timezone
import model_utils.fields


def activity(apps, schema_editor):
    """
    Create default Project Types
    """
    ProjectType = apps.get_model('lims', 'ProjectType')
    db_alias = schema_editor.connection.alias
    to_create = [
        ProjectType(
            name='Academic',
            description="Users from Academic institutions with general peer-reviewed access",
        ),
        ProjectType(
            name='Industry',
            description="Industrial clients using purchased access",
        ),
        ProjectType(
            name='Staff',
            description="Staff Projects",
        ),
        ProjectType(
            name='Student',
            description="Projects created for use by students during workshops/courses",
        ),
        ProjectType(
            name='Commissioning',
            description="Projects used for beamline commissioning",
        ),
    ]

    # create new datatype objects
    ProjectType.objects.using(db_alias).bulk_create(to_create)


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0040_guide'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.RunPython(activity)
    ]