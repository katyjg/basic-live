from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0009_facilitymodetype_and_refactor_facilitymode"),
    ]

    operations = [
        migrations.AddField(
            model_name="beamlinesupport",
            name="source_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=100,
                null=True,
                verbose_name="External Source ID",
            ),
        ),
        migrations.AddField(
            model_name="beamtime",
            name="source_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=100,
                null=True,
                verbose_name="External Source ID",
            ),
        ),
        migrations.AddField(
            model_name="downtime",
            name="source_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=100,
                null=True,
                verbose_name="External Source ID",
            ),
        ),
    ]
