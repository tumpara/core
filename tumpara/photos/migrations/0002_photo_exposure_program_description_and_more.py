# Generated by Django 4.1.4 on 2023-01-24 12:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='photo',
            name='exposure_program_description',
            field=models.CharField(blank=True, help_text='As named or identified by the camera vendor. This may be blank.', max_length=100, verbose_name='exposure program'),
        ),
        migrations.AddField(
            model_name='photo',
            name='flash_description',
            field=models.CharField(blank=True, help_text='As named or identified by the camera vendor. This may be blank.', max_length=100, verbose_name='flash'),
        ),
        migrations.AddField(
            model_name='photo',
            name='focus_mode_description',
            field=models.CharField(blank=True, help_text='As named or identified by the camera vendor. This may be blank.', max_length=100, verbose_name='focus mode'),
        ),
        migrations.AddField(
            model_name='photo',
            name='lens_identifier',
            field=models.CharField(blank=True, max_length=100, verbose_name='lens identifier'),
        ),
        migrations.AddField(
            model_name='photo',
            name='macro_mode_description',
            field=models.CharField(blank=True, help_text='As named or identified by the camera vendor. This may be blank.', max_length=100, verbose_name='macro mode'),
        ),
        migrations.AddField(
            model_name='photo',
            name='metering_mode_description',
            field=models.CharField(blank=True, help_text='As named or identified by the camera vendor. This may be blank.', max_length=100, verbose_name='metering mode'),
        ),
        migrations.AddField(
            model_name='photo',
            name='software',
            field=models.CharField(blank=True, max_length=100, verbose_name='software'),
        ),
    ]
