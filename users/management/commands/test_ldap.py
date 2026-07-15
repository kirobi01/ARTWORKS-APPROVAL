from django.core.management.base import BaseCommand

from users.ldap_client import diagnose_ldap, ldap_is_available


class Command(BaseCommand):
    help = 'Diagnose Active Directory / LDAP connectivity and optional user bind'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='', help='Optional AD username to test login bind')
        parser.add_argument('--password', default='', help='Optional AD password to test login bind')

    def handle(self, *args, **options):
        if not ldap_is_available():
            self.stderr.write(self.style.ERROR('No LDAP library available (install ldap3)'))
            return

        report = diagnose_ldap(
            username=options.get('username') or None,
            password=options.get('password') or None,
        )

        for key, value in report.items():
            if key == 'error' and not value:
                continue
            line = f'{key}: {value}'
            if key in {'tcp_ok', 'service_bind_ok', 'user_bind_ok', 'ldap_enabled'} and value:
                self.stdout.write(self.style.SUCCESS(line))
            elif key in {'tcp_ok', 'service_bind_ok', 'user_bind_ok'} and value is False:
                self.stdout.write(self.style.ERROR(line))
            elif key == 'error' and value:
                self.stdout.write(self.style.ERROR(line))
            else:
                self.stdout.write(line)

        if report.get('tcp_ok') and report.get('service_bind_ok') is False and report.get('bind_password_set'):
            self.stdout.write(self.style.WARNING(
                'Hint: if LDAP_PASSWORD contains # or $, wrap it in double quotes in .env and recreate containers.'
            ))
        if report.get('tcp_ok') is False:
            self.stdout.write(self.style.WARNING(
                'Hint: from the server run: docker compose exec web python -c '
                '"import socket; socket.create_connection((\'10.0.0.4\',389),5); print(\'ok\')"'
            ))
