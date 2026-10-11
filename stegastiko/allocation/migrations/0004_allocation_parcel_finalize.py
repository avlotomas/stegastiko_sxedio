"""Step 3/3: drop the legacy Parcel FK and rename approved_design_plot to parcel."""

from django.db import migrations, models
import django.db.models.deletion

TABLE = "allocation_allocation"
NEW_COLUMN = "approved_design_plot_id"


def _has_new_column(schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if TABLE not in connection.introspection.table_names(cursor):
            return False
        columns = connection.introspection.get_table_description(cursor, TABLE)
    return any(column.name == NEW_COLUMN for column in columns)


class SchemaChangesIfNotYetApplied(migrations.SeparateDatabaseAndState):
    """Always updates migration state; touches the database only if it is not final yet.

    A database that applied the former monolithic allocation 0002 already has these changes
    (no approved_design_plot_id column), so re-running them would fail. Reversal is
    unconditional because both histories end in the same final schema.
    """

    def __init__(self, operations):
        super().__init__(database_operations=operations, state_operations=operations)

    def deconstruct(self):
        return (
            "SeparateDatabaseAndState",
            [],
            {
                "database_operations": self.database_operations,
                "state_operations": self.state_operations,
            },
        )

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if _has_new_column(schema_editor):
            super().database_forwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):
    dependencies = [
        ("allocation", "0003_allocation_plot_links_data"),
    ]

    operations = [
        SchemaChangesIfNotYetApplied(
            [
                migrations.RemoveField(model_name="allocation", name="parcel"),
                migrations.RenameField(
                    model_name="allocation",
                    old_name="approved_design_plot",
                    new_name="parcel",
                ),
                migrations.AlterField(
                    model_name="allocation",
                    name="parcel",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="allocations",
                        to="cases.approveddesignplot",
                    ),
                ),
            ]
        ),
    ]
