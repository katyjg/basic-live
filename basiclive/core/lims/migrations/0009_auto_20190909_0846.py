# Generated by Django 2.2.5 on 2019-09-09 14:46

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0008_auto_20190908_1044'),
    ]

    operations = [
        migrations.AlterField(
            model_name='container',
            name='location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='contents', to='lims.ContainerLocation'),
        ),
        migrations.AlterField(
            model_name='sample',
            name='container',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='samples', to='lims.Container'),
        ),
        migrations.AlterField(
            model_name='sample',
            name='group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='samples', to='lims.Group'),
        ),
        migrations.AlterField(
            model_name='sample',
            name='project',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='samples', to=settings.AUTH_USER_MODEL),
        ),
    ]
