# Generated by Django 3.0.6 on 2020-05-19 22:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0053_auto_20200519_1641'),
    ]

    operations = [
        migrations.AlterField(
            model_name='beamline',
            name='active',
            field=models.BooleanField(default=True),
        ),
    ]
