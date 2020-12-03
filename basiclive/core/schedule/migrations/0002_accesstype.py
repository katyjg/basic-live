# Generated by Django 3.0.4 on 2020-03-24 22:35

from django.db import migrations


def activity(apps, schema_editor):
    """
    Create default Project Types
    """
    AccessType = apps.get_model('schedule', 'AccessType')
    db_alias = schema_editor.connection.alias
    to_create = [
        AccessType(
            name='Mail-In',
            color='#8F3A84',
            email_subject="Mail-In Data Collection",
            email_body="",
        ),
        AccessType(
            name='Remote',
            color='#17A2B8',
            email_subject="Remote Data Collection",
            email_body="",
        ),
        AccessType(
            name='Local',
            color='#FFC107',
            email_subject="Data Collection",
            email_body="",
        ),
    ]

    # create new accesstype objects
    AccessType.objects.using(db_alias).bulk_create(to_create)


class Migration(migrations.Migration):

    dependencies = [
        ('schedule', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(activity)
    ]