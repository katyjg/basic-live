# Generated by Django 2.2.6 on 2019-12-02 22:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lims', '0033_auto_20191111_0939'),
    ]

    operations = [
        migrations.DeleteModel(
            name='SpaceGroup',
        ),
        migrations.AlterModelOptions(
            name='container',
            options={'ordering': ('kind', 'location', 'name')},
        ),
        migrations.AlterField(
            model_name='datatype',
            name='acronym',
            field=models.SlugField(unique=True),
        ),
    ]
