from django.db import migrations, models


def forwards_update_role(apps, schema_editor):
    ProjectMembership = apps.get_model('lims', 'ProjectMembership')
    ProjectMembership.objects.filter(role='CO_INVESTIGATOR').update(role='DELEGATE')


def backwards_update_role(apps, schema_editor):
    ProjectMembership = apps.get_model('lims', 'ProjectMembership')
    ProjectMembership.objects.filter(role='DELEGATE').update(role='CO_INVESTIGATOR')


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0126_rename_name_project_code_project_title'),
    ]

    operations = [
        migrations.RunPython(forwards_update_role, backwards_update_role),
        migrations.AlterField(
            model_name='projectmembership',
            name='role',
            field=models.CharField(
                choices=[('PI', 'Principal Investigator'), ('DELEGATE', 'Delegate'), ('MEMBER', 'Member')],
                default='MEMBER',
                max_length=20,
            ),
        ),
    ]
