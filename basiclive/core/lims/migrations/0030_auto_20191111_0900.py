# Generated by Django 2.2.5 on 2019-11-11 15:00

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0029_datatype'),
    ]

    operations = [
        migrations.RenameField(
            model_name='data',
            old_name='kind',
            new_name='kind_outgoing',
        ),
    ]