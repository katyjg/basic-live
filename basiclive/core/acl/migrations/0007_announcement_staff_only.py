# Generated by Django 2.2.5 on 2019-12-13 04:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('acl', '0006_auto_20190907_2214'),
    ]

    operations = [
        migrations.AddField(
            model_name='announcement',
            name='staff_only',
            field=models.BooleanField(default=False),
        ),
    ]

    replaces = [('staff', '0007_announcement_staff_only')]