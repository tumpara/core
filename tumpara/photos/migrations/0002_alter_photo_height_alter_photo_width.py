# Generated by Django 4.0.4 on 2022-05-22 09:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('photos', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='photo',
            name='height',
            field=models.PositiveIntegerField(null=True, verbose_name='height'),
        ),
        migrations.AlterField(
            model_name='photo',
            name='width',
            field=models.PositiveIntegerField(null=True, verbose_name='width'),
        ),
    ]
