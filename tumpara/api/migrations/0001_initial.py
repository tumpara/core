# Generated by Django 4.0.3 on 2022-05-14 14:42

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.crypto
import functools


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Token',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(default=functools.partial(django.utils.crypto.get_random_string, *(32,), **{}), max_length=32, unique=True, verbose_name='key')),
                ('expiry_timestamp', models.DateTimeField(help_text='The token will become invalid after this timestamp.', null=True, verbose_name='valid until')),
                ('name', models.CharField(blank=True, help_text='Human-readable name for this token.', max_length=100, verbose_name='name')),
                ('creation_timestamp', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
                ('usage_timestamp', models.DateTimeField(auto_now=True, verbose_name='last used')),
                ('user', models.ForeignKey(help_text='The user connected to the token. Any actions will be performed in their name.', on_delete=django.db.models.deletion.CASCADE, related_name='api_tokens', related_query_name='api_token', to=settings.AUTH_USER_MODEL, verbose_name='user')),
            ],
            options={
                'verbose_name': 'API token',
                'verbose_name_plural': 'API tokens',
            },
        ),
    ]
