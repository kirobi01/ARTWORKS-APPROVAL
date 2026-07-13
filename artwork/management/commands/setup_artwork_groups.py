from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group


class Command(BaseCommand):
    help = 'Create Django groups for the Artwork Approval workflow'

    def handle(self, *args, **options):
        groups = [
            'DESIGN', 'MARKETING_SALES', 'QUALITY_ASSURANCE', 'OPERATIONS_HOD',
            'PRODUCT_DEVELOPMENT', 'MILAN', 'PROCUREMENT', 'ADMIN',
        ]
        for name in groups:
            Group.objects.get_or_create(name=name)
            self.stdout.write(self.style.SUCCESS(f'Group ready: {name}'))
