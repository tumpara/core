# Generated by Django 4.2.1 on 2023-06-11 16:20

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("libraries", "0004_alter_collection_title_alter_collectionitem_asset"),
    ]

    operations = [
        migrations.AddField(
            model_name="file",
            name="extra",
            field=models.CharField(
                blank=True,
                help_text="Extra information on this specific file. The content and format of this value depends on the asset type. This is intended to be machine-readable.",
                max_length=100,
                verbose_name="extra information",
            ),
        ),
    ]
