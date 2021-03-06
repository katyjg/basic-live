# Generated by Django 3.1.4 on 2021-02-05 17:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0091_auto_20210201_1547'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='sample',
            options={'ordering': ['group__priority', 'priority', 'container__name', 'location__pk', 'name']},
        ),
        migrations.RenameField(
            model_name='requesttype',
            old_name='template',
            new_name='edit_template',
        ),
        migrations.AddField(
            model_name='requesttype',
            name='view_template',
            field=models.CharField(default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='requesttype',
            name='layout',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
