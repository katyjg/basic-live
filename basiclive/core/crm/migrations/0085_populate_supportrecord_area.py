from django.db import migrations


def populate_area_from_areas(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SupportRecord = apps.get_model('crm', 'SupportRecord')
    # Evaluate list upfront so newly created duplicate records are not processed
    for record in list(SupportRecord.objects.using(db_alias).all()):
        areas = list(record.areas.all())
        if not areas:
            continue

        # Assign the first area to the existing record
        record.area = areas[0]

        # fix record kind based on lost_time
        if record.lost_time > 0:
            record.kind = 'problem'
        record.save(update_fields=['area', 'kind'])

        # Duplicate the record for each additional area
        for extra_area in areas[1:]:
            SupportRecord.objects.using(db_alias).create(
                kind=record.kind,
                area=extra_area,
                staff_id=record.staff_id,
                user_id=record.user_id,
                project_id=record.project_id,
                beamline_id=record.beamline_id,
                comments=record.comments,
                lost_time=record.lost_time,
                staff_comments=record.staff_comments,
                created=record.created,
                modified=record.modified,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0084_supportrecord_area'),
    ]

    operations = [
        migrations.RunPython(populate_area_from_areas, migrations.RunPython.noop),
    ]
