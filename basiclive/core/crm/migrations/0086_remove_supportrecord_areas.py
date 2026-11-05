from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0085_populate_supportrecord_area'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='supportrecord',
            name='areas',
        ),
    ]
