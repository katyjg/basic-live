# Generated by Django 3.0.1 on 2019-12-31 22:58

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0041_projecttype'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='kind',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='lims.ProjectType'),
        ),
    ]