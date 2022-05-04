# Generated by Django 4.0.3 on 2022-05-01 14:21

from django.db import migrations, models
import django.utils.timezone
import tumpara.libraries.models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('libraries', '0002_remove_record_record_unique_for_content_type_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='record',
            options={'verbose_name': 'record', 'verbose_name_plural': 'records'},
        ),
        migrations.AddField(
            model_name='record',
            name='import_timestamp',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, help_text='Timestamp when the record was created / imported.', verbose_name='add timestamp'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='record',
            name='uuid',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='UUID'),
        ),
        migrations.AlterField(
            model_name='library',
            name='default_visibility',
            field=models.PositiveSmallIntegerField(choices=[(0, 'Public'), (1, 'All logged-in users'), (2, 'Library members'), (3, 'Only library owners'), (10, 'Use the default value')], default=2, help_text='Default visibility value for records where it is not defined.', validators=[tumpara.libraries.models.validate_library_default_visibility], verbose_name='default visibility'),
        ),
        migrations.AlterField(
            model_name='record',
            name='visibility',
            field=models.PositiveSmallIntegerField(choices=[(0, 'Public'), (1, 'All logged-in users'), (2, 'Library members'), (3, 'Only library owners'), (10, 'Use the default value')], default=10, help_text='Determines who can see this object.', verbose_name='visibility'),
        ),
        migrations.AddIndex(
            model_name='record',
            index=models.Index(fields=['id', 'visibility', 'library'], name='library_visibility_filtering'),
        ),
    ]