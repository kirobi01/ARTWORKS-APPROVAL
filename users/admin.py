from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.urls import path

from .models import Profile, Role, LDAPSyncLog
from . import admin_views


@admin.register(LDAPSyncLog)
class LDAPSyncLogAdmin(admin.ModelAdmin):
    list_display = [
        'started_at', 'success', 'created_count', 'updated_count',
        'skipped_count', 'errors_count', 'triggered_by', 'dry_run',
    ]
    list_filter = ['success', 'dry_run']
    readonly_fields = [
        'started_at', 'completed_at', 'triggered_by', 'dry_run', 'update_existing',
        'created_count', 'updated_count', 'skipped_count', 'errors_count',
        'total_ldap_entries', 'success', 'message',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fk_name = 'user'
    readonly_fields = ['ldap_dn']
    fields = ['department', 'position', 'email', 'extension_no', 'ldap_dn', 'is_active', 'roles']


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ['username', 'email', 'first_name', 'last_name', 'department_display', 'is_staff', 'is_active']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'groups']

    @admin.display(description='Department')
    def department_display(self, obj):
        if hasattr(obj, 'profile'):
            return obj.profile.department or '—'
        return '—'


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'department', 'position', 'email', 'is_active']
    search_fields = ['user__username', 'email', 'ldap_dn', 'department']
    readonly_fields = ['ldap_dn']
    filter_horizontal = ['roles']


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'level']


# Re-register User with profile inline
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


def _patch_admin_urls():
    original = admin.site.get_urls

    def get_urls():
        custom = [
            path(
                'sync-ldap/',
                admin.site.admin_view(admin_views.sync_ldap_view),
                name='sync_ldap_users',
            ),
        ]
        return custom + original()

    admin.site.get_urls = get_urls


_patch_admin_urls()

# Show last LDAP sync on admin home page
_original_each_context = admin.site.each_context


def _each_context_with_sync(request):
    context = _original_each_context(request)
    try:
        from users.models import LDAPSyncLog
        context['last_sync'] = LDAPSyncLog.objects.first()
    except Exception:
        context['last_sync'] = None
    return context


admin.site.each_context = _each_context_with_sync

# Customize admin branding
admin.site.site_header = 'Kapa Oil Refineries — Artwork Administration'
admin.site.site_title = 'Kapa Artwork Admin'
admin.site.index_title = 'System Management'

# Add link on admin index via template override (templates/admin/index.html)
