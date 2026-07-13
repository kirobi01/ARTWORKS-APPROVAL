from django.contrib import messages
from django.shortcuts import render

from django.conf import settings
from users.ldap_sync import run_ldap_sync
from users.models import LDAPSyncLog


def sync_ldap_view(request):
    """Admin page with button to sync users from Active Directory."""
    last_sync = LDAPSyncLog.objects.first()
    recent_syncs = LDAPSyncLog.objects.all()[:10]

    if request.method == 'POST':
        dry_run = request.POST.get('dry_run') == 'on'
        update_existing = request.POST.get('update_existing', 'on') == 'on'

        result = run_ldap_sync(
            dry_run=dry_run,
            update_existing=update_existing,
            verbose=True,
            triggered_by=request.user,
            log_model=True,
        )

        level = messages.SUCCESS if result.success else messages.ERROR
        messages.add_message(request, level, result.message)

        return render(request, 'admin/sync_ldap.html', {
            'title': 'Sync Active Directory Users',
            'result': result,
            'last_sync': LDAPSyncLog.objects.first(),
            'recent_syncs': LDAPSyncLog.objects.all()[:10],
            'opts': LDAPSyncLog._meta,
            'has_permission': True,
            'settings': settings,
        })

    return render(request, 'admin/sync_ldap.html', {
        'title': 'Sync Active Directory Users',
        'result': None,
        'last_sync': last_sync,
        'recent_syncs': recent_syncs,
        'opts': LDAPSyncLog._meta,
        'has_permission': True,
        'settings': settings,
    })
