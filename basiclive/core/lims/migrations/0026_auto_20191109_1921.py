# Generated by Django 2.2.5 on 2019-11-10 01:21

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0025_auto_20191109_1833'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='sample',
            unique_together={('container', 'location')},
        ),
    ]
