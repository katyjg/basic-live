# Generated by Django 3.1.3 on 2020-12-03 19:56

from django.db import migrations


def activity(apps, schema_editor):
    """
    Fix names and kinds of Data Analysis Reports
    """
    DataType = apps.get_model('lims', 'DataType')
    db_alias = schema_editor.connection.alias

    for dt in DataType.objects.using(db_alias).filter(template__startswith='users/'):
        dt.template = dt.template.replace('users/', 'lims/')
        dt.save()


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0078_merge_20201202_1618'),
    ]

    operations = [
        migrations.RunPython(activity)
    ]