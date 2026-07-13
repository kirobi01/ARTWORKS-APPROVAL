from django.core.management.base import BaseCommand

from users.account_utils import deduplicate_users


class Command(BaseCommand):
    help = 'Merge case-insensitive duplicate Django users and normalize usernames.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would change without writing to the database.',
        )

    def handle(self, *args, **options):
        merged, normalized = deduplicate_users(dry_run=options['dry_run'])
        prefix = 'Would merge' if options['dry_run'] else 'Merged'
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefix} {merged} duplicate username group(s); '
                f'normalized {normalized} username(s).'
            )
        )
