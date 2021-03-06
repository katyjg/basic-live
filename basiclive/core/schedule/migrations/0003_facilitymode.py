# Generated by Django 3.0.6 on 2020-05-19 23:00

import colorfield.fields
from django.db import migrations, models


def create_modes(apps, schema_editor):
    """
    Create default Facility Modes
    """
    FacilityMode = apps.get_model('schedule', 'FacilityMode')

    db_alias = schema_editor.connection.alias
    to_create = [
        FacilityMode(
            kind="N",
            description="Normal",
            color="#E1F0B3"
        ),
        FacilityMode(
            kind="D",
            description="Development",
            color="#ffe1b3"
        ),
        FacilityMode(
            kind="M, MV, M0, MT",
            description="Maintenance",
            color="#ccf5ff"
        ),
        FacilityMode(
            kind="DS, DST, DS-CSR",
            description="Special Development",
            color="#F0D7B3"
        ),
        FacilityMode(
            kind="X",
            description="Shutdown (Beam Off)",
            color="#FEFEAD"
        ),
        FacilityMode(
            kind="NS",
            description="Special Beam",
            color="#D5E1B3"
        )
    ]

    FacilityMode.objects.using(db_alias).bulk_create(to_create)


class Migration(migrations.Migration):

    dependencies = [
        ('schedule', '0002_accesstype'),
    ]

    operations = [
        migrations.CreateModel(
            name='FacilityMode',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(max_length=30)),
                ('description', models.CharField(blank=True, max_length=60)),
                ('color', colorfield.fields.ColorField(default='#000000', max_length=18)),
            ],
        ),
        migrations.RunPython(create_modes)
    ]
