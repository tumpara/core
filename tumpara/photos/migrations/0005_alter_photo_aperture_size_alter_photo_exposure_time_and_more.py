# Generated by Django 4.0.4 on 2022-06-03 16:16

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0004_photo_main_path'),
    ]

    operations = [
        migrations.AlterField(
            model_name='photo',
            name='aperture_size',
            field=models.DecimalField(decimal_places=1, help_text='Aperture / F-Stop value of the shot, in inverse. A value of 4 in this field implies an f-value of f/4.', max_digits=3, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], verbose_name='aperture size'),
        ),
        migrations.AlterField(
            model_name='photo',
            name='exposure_time',
            field=models.FloatField(help_text="The shot's exposure time, in seconds.", null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='exposure time'),
        ),
        migrations.AlterField(
            model_name='photo',
            name='focal_length',
            field=models.FloatField(help_text='Focal length of the camera, in millimeters.', null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='focal length'),
        ),
    ]