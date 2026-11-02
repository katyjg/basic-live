from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lims", "0124_populate_system_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="source_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=100,
                null=True,
                unique=True,
                verbose_name="External Source ID",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="start_date",
            field=models.DateField(blank=True, null=True, verbose_name="Start Date"),
        ),
        migrations.AddField(
            model_name="project",
            name="end_date",
            field=models.DateField(blank=True, null=True, verbose_name="End Date"),
        ),
        migrations.AddField(
            model_name="project",
            name="external_roster",
            field=models.JSONField(blank=True, default=list, verbose_name="External Roster"),
        ),
    ]
