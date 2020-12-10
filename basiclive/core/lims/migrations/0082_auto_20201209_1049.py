# Generated by Django 3.1.4 on 2020-12-09 16:49

from django.db import migrations, models
from django.db.models import Value
from django.db.models.functions import Replace


def fix_json(apps, schema_editor):
    """
    Convert NaN values to null before converting field type
    """
    to_fix = [
        ('AnalysisReport', 'details'),
        ('ContainerType', 'layout'),
        ('Data', 'meta_data'),
        ('DataType', 'metadata')
    ]
    for name, field in to_fix:
        model_class = apps.get_model('lims', name)
        db_alias = schema_editor.connection.alias

        model_class.objects.using(db_alias).filter(**{f'{field}__contains': 'NaN'}).update(
            **{field: Replace(field, Value('NaN'), Value('null'))}
        )


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0081_auto_20201207_1243'),
    ]

    operations = [
        migrations.RunPython(fix_json),

        migrations.AlterField(
            model_name='analysisreport',
            name='details',
            field=models.JSONField(default=list),
        ),
        migrations.AlterField(
            model_name='containertype',
            name='layout',
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name='data',
            name='meta_data',
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name='datatype',
            name='metadata',
            field=models.JSONField(default=list),
        ),
    ]