# Generated by Django 3.1.5 on 2021-01-28 16:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0086_auto_20210128_1052'),
    ]

    operations = [
        migrations.AddField(
            model_name='requesttype',
            name='active',
            field=models.BooleanField(default=True),
        ),
    ]
