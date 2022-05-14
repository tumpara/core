# Generated by Django 4.0.4 on 2022-05-14 14:43

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('libraries', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='GenericHandler',
            fields=[
                ('asset', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, related_name='%(class)s_instance', related_query_name='%(class)s_instance', serialize=False, to='libraries.asset', verbose_name='asset reference')),
                ('initialized', models.BooleanField(default=False)),
                ('content', models.BinaryField()),
            ],
            options={
                'abstract': False,
            },
            bases=('libraries.asset',),
        ),
    ]
