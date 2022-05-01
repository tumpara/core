from django.db import migrations


def fix_spacialite_compatability(apps, schema_editor):
    """Try and fix compatibility issues between SpaciaLite and the newest versino of
    SQLite.

    See here for details:
    https://groups.google.com/g/spatialite-users/c/azalHqVOPg0/m/JXIu9sn6BAAJ
    """
    if not schema_editor.connection.vendor.startswith("sqlite"):
        return

    # Use 'IF EXISTS' here in case SpaciaLite isn't actually enabled:
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS ISO_metadata_reference_row_id_value_insert;"
    )
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS ISO_metadata_reference_row_id_value_update;"
    )


class Migration(migrations.Migration):
    run_before = [
        # This migration must run before *all* other migrations.
        ("contenttypes", "0001_initial"),
        ("auth", "0001_initial"),
        ("sessions", "0001_initial"),
        ("accounts", "0001_initial"),
        ("api", "0001_initial"),
    ]

    operations = [migrations.RunPython(fix_spacialite_compatability)]
