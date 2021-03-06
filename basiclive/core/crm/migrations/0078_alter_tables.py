# Generated by Django 3.1.3 on 2020-12-02 22:19

from django.db import migrations


def fix_content_type(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    db_alias = schema_editor.connection.alias
    old_models = ['supportrecord', 'feedbackscale', 'userfeedback', 'userareafeedback']
    ContentType.objects.using(db_alias).filter(app_label='lims', model__in=old_models).update(app_label='crm')


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0077_merge_20201202_1619'),
    ]

    operations = [
        migrations.RunPython(fix_content_type),
        migrations.AlterModelTable('supportrecord', 'crm_supportrecord'),
        migrations.AlterModelTable('feedbackscale', 'crm_feedbackscale'),
        migrations.AlterModelTable('userfeedback', 'crm_userfeedback'),
        migrations.AlterModelTable('userareafeedback', 'crm_userareafeedback'),
    ]

    replaces = [
        ('lims', '0078_alter_tables'),
    ]
