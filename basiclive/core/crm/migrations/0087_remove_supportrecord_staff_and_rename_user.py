# Generated migration to remove legacy SupportRecord.staff (Project) and rename user (User) to staff

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0086_remove_supportrecord_areas'),
        ('lims', '0104_migrate_project_users_data'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name='supportrecord',
            name='staff',
        ),
        migrations.RenameField(
            model_name='supportrecord',
            old_name='user',
            new_name='staff',
        ),
        migrations.AlterField(
            model_name='supportrecord',
            name='staff',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='support_records',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
