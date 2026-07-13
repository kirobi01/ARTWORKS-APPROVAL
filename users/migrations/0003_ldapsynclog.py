from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('users', '0002_profile_ldap_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='LDAPSyncLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('dry_run', models.BooleanField(default=False)),
                ('update_existing', models.BooleanField(default=True)),
                ('created_count', models.PositiveIntegerField(default=0)),
                ('updated_count', models.PositiveIntegerField(default=0)),
                ('skipped_count', models.PositiveIntegerField(default=0)),
                ('errors_count', models.PositiveIntegerField(default=0)),
                ('total_ldap_entries', models.PositiveIntegerField(default=0)),
                ('success', models.BooleanField(default=False)),
                ('message', models.TextField(blank=True)),
                ('triggered_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='ldap_syncs', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-started_at']},
        ),
    ]
