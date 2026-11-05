from django.db import migrations, models


def migrate_selections_to_quote(apps, schema_editor):
    Annotation = apps.get_model('notebooks', 'Annotation')
    for annotation in Annotation.objects.all():
        selections = getattr(annotation, 'selections', None)
        if selections and isinstance(selections, list):
            annotation.quote = '\n'.join(str(s) for s in selections if s)
        if not annotation.text:
            annotation.text = "Highlighted text"
        annotation.save(update_fields=['quote', 'text'])


def reverse_migrate(apps, schema_editor):
    Annotation = apps.get_model('notebooks', 'Annotation')
    for annotation in Annotation.objects.all():
        if annotation.quote:
            annotation.selections = annotation.quote.split('\n')
        annotation.save(update_fields=['selections'])


class Migration(migrations.Migration):

    dependencies = [
        ('notebooks', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='annotation',
            name='quote',
            field=models.TextField(blank=True, default='', verbose_name='Quote'),
        ),
        migrations.RunPython(migrate_selections_to_quote, reverse_code=reverse_migrate),
        migrations.AlterField(
            model_name='annotation',
            name='text',
            field=models.TextField(verbose_name='Comment text'),
        ),
        migrations.RemoveField(
            model_name='annotation',
            name='kind',
        ),
        migrations.RemoveField(
            model_name='annotation',
            name='node_index',
        ),
        migrations.RemoveField(
            model_name='annotation',
            name='selections',
        ),
    ]
