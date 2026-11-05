# Generated migration to remove legacy BeamlineSupport.staff (Project) and rename user (User) to staff

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schedule', '0007_alter_accesstype_options_and_more'),
        ('lims', '0104_migrate_project_users_data'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name='beamlinesupport',
            name='staff',
        ),
        migrations.RenameField(
            model_name='beamlinesupport',
            old_name='user',
            new_name='staff',
        ),
        migrations.AlterField(
            model_name='beamlinesupport',
            name='staff',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='support',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
