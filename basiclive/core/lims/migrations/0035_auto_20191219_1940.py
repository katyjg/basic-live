# Generated by Django 2.2.5 on 2019-12-20 01:40

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0034_auto_20191202_1620'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='session',
            options={'ordering': ('-created',)},
        ),
    ]