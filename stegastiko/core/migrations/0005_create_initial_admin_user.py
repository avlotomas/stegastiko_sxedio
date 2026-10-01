from django.contrib.auth.hashers import make_password
from django.db import migrations


def create_initial_admin_user(apps, schema_editor):
    User = apps.get_model("auth", "User")
    if User.objects.filter(username="admin").exists():
        return
    User.objects.create(
        username="admin",
        password=make_password("1234"),
        is_staff=True,
        is_superuser=True,
        is_active=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_seed_default_system_settings"),
    ]

    operations = [
        migrations.RunPython(create_initial_admin_user, migrations.RunPython.noop),
    ]
