import colorfield.fields
import django.db.models.deletion
from django.db import migrations, models


def seed_facility_mode_types(apps, schema_editor):
    FacilityModeType = apps.get_model("schedule", "FacilityModeType")
    db_alias = schema_editor.connection.alias

    canonical_modes = [
        ("normal", "Normal", "#E1F0B3"),
        ("development", "Development", "#FFE1B3"),
        ("maintenance", "Maintenance", "#CCF5FF"),
        ("shutdown", "Shutdown (Beam Off)", "#FEFEAD"),
        ("special", "Special Beam", "#D5E1B3"),
    ]
    for code, description, color in canonical_modes:
        FacilityModeType.objects.using(db_alias).update_or_create(
            code=code,
            defaults={"description": description, "color": color},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0008_remove_beamlinesupport_staff_and_rename_user"),
    ]

    operations = [
        migrations.CreateModel(
            name="FacilityModeType",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.SlugField(max_length=30, unique=True)),
                ("description", models.CharField(blank=True, max_length=60)),
                (
                    "color",
                    colorfield.fields.ColorField(
                        default="#000000", image_field=None, max_length=25, samples=None
                    ),
                ),
            ],
            options={
                "verbose_name": "Facility Mode Type",
                "verbose_name_plural": "Facility Mode Types",
                "ordering": ["code"],
            },
        ),
        migrations.RunPython(seed_facility_mode_types, migrations.RunPython.noop),
        migrations.DeleteModel(
            name="FacilityMode",
        ),
        migrations.CreateModel(
            name="FacilityMode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "start",
                    models.DateTimeField(blank=True, null=True, verbose_name="start"),
                ),
                (
                    "end",
                    models.DateTimeField(blank=True, null=True, verbose_name="end"),
                ),
                ("comments", models.TextField(blank=True)),
                (
                    "source_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=100,
                        null=True,
                        verbose_name="External Source ID",
                    ),
                ),
                (
                    "mode",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="intervals",
                        to="schedule.facilitymodetype",
                    ),
                ),
            ],
            options={
                "verbose_name": "Facility Mode",
                "verbose_name_plural": "Facility Modes",
                "ordering": ["start"],
            },
        ),
    ]
