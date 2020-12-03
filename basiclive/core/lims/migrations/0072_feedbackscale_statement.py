# Generated by Django 3.0.6 on 2020-07-31 16:48

from django.db import migrations, models


def initialize_scale(apps, schema_editor):
    FeedbackScale = apps.get_model('lims', 'FeedbackScale')
    SupportArea = apps.get_model('lims', 'SupportArea')
    db_alias = schema_editor.connection.alias
    scale = FeedbackScale.objects.using(db_alias).create(statement='Please evaluate the following aspects of your recent beamline experience.',
                                                 worst='Needs Urgent Attention', worse='Needs Improvement',
                                                 better='Satisfied', best='Impressed')
    SupportArea.objects.update(scale=scale)


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0071_auto_20200731_1044'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedbackscale',
            name='statement',
            field=models.CharField(max_length=250, null=True),
        ),
        migrations.RunPython(initialize_scale),
    ]