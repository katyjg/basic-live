# Generated by Django 3.0.6 on 2020-07-10 19:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0056_populate_container_type'),
        ('acl', '0012_delete_usercategory'),
    ]

    operations = [
        migrations.AddField(
            model_name='userlist',
            name='beamline',
            field=models.ManyToManyField(blank=True, to='lims.Beamline'),
        ),
    ]

    replaces = [('staff', '0013_userlist_beamline')]