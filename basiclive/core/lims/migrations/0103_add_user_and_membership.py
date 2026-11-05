import django.contrib.auth.models
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
from django.conf import settings
from django.db import migrations, models


def create_user_table_if_not_exists(apps, schema_editor):
    table_names = schema_editor.connection.introspection.table_names()
    User = apps.get_model('lims', 'User')
    if User._meta.db_table not in table_names:
        schema_editor.create_model(User)


def drop_user_table_if_exists(apps, schema_editor):
    table_names = schema_editor.connection.introspection.table_names()
    User = apps.get_model('lims', 'User')
    if User._meta.db_table in table_names:
        schema_editor.delete_model(User)


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('lims', '0102_create_default_requesttypes'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(create_user_table_if_not_exists, reverse_code=drop_user_table_if_exists),
            ],
            state_operations=[],
        ),
        migrations.AddField(
            model_name='project',
            name='pi',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='led_projects',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name='sshkey',
            name='user',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='sshkeys', to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.CreateModel(
            name='ProjectMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(
                    default=django.utils.timezone.now, editable=False, verbose_name='created'
                )),
                ('modified', model_utils.fields.AutoLastModifiedField(
                    default=django.utils.timezone.now, editable=False, verbose_name='modified'
                )),
                ('role', models.CharField(
                    choices=[
                        ('PI', 'Principal Investigator'), ('CO_INVESTIGATOR', 'Co-Investigator'), ('MEMBER', 'Member')
                    ],
                    default='MEMBER', max_length=20
                )),
                ('project', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='lims.project'
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to=settings.AUTH_USER_MODEL
                )),
            ],
            options={
                'verbose_name': 'Project Membership',
                'verbose_name_plural': 'Project Memberships',
                'unique_together': {('user', 'project')},
            },
        ),
        migrations.AddField(
            model_name='project',
            name='members',
            field=models.ManyToManyField(
                blank=True, related_name='projects', through='lims.ProjectMembership', to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AlterField(
            model_name='project',
            name='created',
            field=model_utils.fields.AutoCreatedField(
                default=django.utils.timezone.now, editable=False, verbose_name='created'
            ),
        ),
        migrations.AlterField(
            model_name='project',
            name='email',
            field=models.EmailField(blank=True, default='', max_length=254),
        ),
        migrations.AlterField(
            model_name='project',
            name='first_name',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AlterField(
            model_name='project',
            name='last_name',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AlterField(
            model_name='project',
            name='modified',
            field=model_utils.fields.AutoLastModifiedField(
                default=django.utils.timezone.now, editable=False, verbose_name='modified'
            ),
        ),
        migrations.AlterField(
            model_name='project',
            name='name',
            field=models.SlugField(max_length=100, unique=True),
        ),
        migrations.AlterField(
            model_name='project',
            name='username',
            field=models.CharField(blank=True, max_length=150, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='sshkey',
            name='project',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='sshkeys', to='lims.project'
            ),
        ),
    ]
