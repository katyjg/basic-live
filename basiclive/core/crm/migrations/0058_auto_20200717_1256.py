# Generated by Django 3.0.6 on 2020-07-17 18:56

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='supportrecord',
            old_name='area',
            new_name='areas',
        ),
    ]

    replaces = [('lims', '0058_auto_20200717_1256')]