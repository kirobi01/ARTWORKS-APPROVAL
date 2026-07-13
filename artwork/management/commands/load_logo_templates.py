from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Load default reusable logo templates (names from fixture; upload icons in Admin)'

    def handle(self, *args, **options):
        call_command('loaddata', 'logo_templates', verbosity=options.get('verbosity', 1))
        self.stdout.write(self.style.SUCCESS(
            'Logo templates loaded. Upload icon images under Admin → Logo templates.'
        ))
