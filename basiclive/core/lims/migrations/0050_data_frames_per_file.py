# Generated by Django 3.0.2 on 2020-02-28 18:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0049_beamline_simulated'),
    ]

    operations = [
        migrations.AddField(
            model_name='data',
            name='frames_per_file',
            field=models.IntegerField(default=1, verbose_name='Maximum Frames per File'),
        ),
    ]
