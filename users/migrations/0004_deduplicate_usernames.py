from django.db import migrations


def dedupe_usernames(apps, schema_editor):
    from users.account_utils import deduplicate_users
    deduplicate_users()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_ldapsynclog'),
    ]

    operations = [
        migrations.RunPython(dedupe_usernames, migrations.RunPython.noop),
    ]
