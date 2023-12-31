# Generated by Django 4.0.4 on 2022-06-03 16:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('libraries', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='file',
            name='path',
            field=models.CharField(db_index=True, help_text='Path of this file, relative to the library root. This should *not* start with a slash.', max_length=255, verbose_name='filename'),
        ),
    ]
