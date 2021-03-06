# Generated by Django 3.1.3 on 2020-12-03 13:25

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0078_alter_tables'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='UserAreaFeedback',
            new_name='AreaFeedback',
        ),
        migrations.RenameModel(
            old_name='UserFeedback',
            new_name='Feedback',
        ),
        migrations.RenameModel(
            old_name='FeedbackScale',
            new_name='LikertScale',
        ),
        migrations.AlterModelOptions(
            name='likertscale',
            options={'verbose_name': 'Likert Scale'},
        ),
        migrations.AlterModelTable(
            name='areafeedback',
            table=None,
        ),
        migrations.AlterModelTable(
            name='feedback',
            table=None,
        ),
        migrations.AlterModelTable(
            name='likertscale',
            table=None,
        ),
        migrations.AlterModelTable(
            name='supportarea',
            table=None,
        ),
        migrations.AlterModelTable(
            name='supportrecord',
            table=None,
        ),
    ]

    replaces = [
        ('lims', '0079_auto_20201203_0725')
    ]
