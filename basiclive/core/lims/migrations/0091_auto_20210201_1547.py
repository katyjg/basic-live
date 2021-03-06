# Generated by Django 3.1.5 on 2021-02-01 21:47

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0090_containertype_active'),
    ]

    operations = [
        migrations.AlterField(
            model_name='containertype',
            name='envelope',
            field=models.CharField(blank=True, choices=[('rect', 'Rectangle'), ('circle', 'Circle'), ('list', 'List')], max_length=200),
        ),
        migrations.AlterField(
            model_name='sample',
            name='location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='samples', to='lims.containerlocation'),
        ),
    ]
