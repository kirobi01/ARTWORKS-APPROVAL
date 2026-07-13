from celery import shared_task
from django.core.management import call_command


@shared_task(name='sync_ldap_users')
def sync_ldap_users_task():
    call_command('sync_ldap_users', update_existing=True)
