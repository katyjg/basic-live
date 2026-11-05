import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0106_activitylog_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='default_project',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='lims.project',
                verbose_name='Default Project',
            ),
        ),
    ]
