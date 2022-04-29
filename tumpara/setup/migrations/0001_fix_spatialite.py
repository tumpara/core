from django.db import migrations


class Migration(migrations.Migration):
    run_before = [
        # This migration must run before *all* other migrations.
        ("contenttypes", "0001_initial"),
        ("auth", "0001_initial"),
        ("sessions", "0001_initial"),
        ("accounts", "0001_initial"),
        ("api", "0001_initial"),
    ]

    operations = [
        # This should fix compatibility issues between SpaciaLite and the newest version
        # of SQLite. See here for details:
        # https://groups.google.com/g/spatialite-users/c/azalHqVOPg0/m/JXIu9sn6BAAJ
        migrations.RunSQL(
            """
            DROP TRIGGER ISO_metadata_reference_row_id_value_insert;
            DROP TRIGGER ISO_metadata_reference_row_id_value_update;
            """
        )
    ]
