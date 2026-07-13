from django.core.management.base import BaseCommand

from users.ldap_sync import run_ldap_sync


class Command(BaseCommand):
    help = 'Sync users from Active Directory into Django (username + profile + department)'

    def add_arguments(self, parser):
        parser.add_argument('--verbose', action='store_true')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--update-existing', action='store_true')

    def handle(self, *args, **options):
        result = run_ldap_sync(
            dry_run=options['dry_run'],
            update_existing=options.get('update_existing', False),
            limit=options.get('limit'),
            verbose=options['verbose'],
            log_model=True,
        )
        if result.log_lines and options['verbose']:
            for line in result.log_lines:
                self.stdout.write(f'  {line}')
        if result.success:
            self.stdout.write(self.style.SUCCESS(result.message))
        else:
            self.stderr.write(self.style.ERROR(result.message))
