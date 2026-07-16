from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.admin.views.autocomplete import AutocompleteJsonView
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.shortcuts import redirect
from django.urls import path, reverse

from .models import Profile, Role, LDAPSyncLog
from . import admin_views
from .ldap_sync import run_ldap_sync


def format_user_choice(user):
    """Show full name with username in admin pickers."""
    if not user:
        return ''
    name = (user.get_full_name() or '').strip()
    if name:
        return f'{name} ({user.username})'
    return user.username


class GroupAdminForm(forms.ModelForm):
    """Expose group membership on the Group change page for easy add/remove."""

    users = forms.ModelMultipleChoiceField(
        label='Members',
        queryset=User.objects.all().order_by('first_name', 'last_name', 'username'),
        required=False,
        widget=FilteredSelectMultiple('members', is_stacked=False),
        help_text='Select people who belong to this group. Search and move them with the arrows.',
    )

    class Meta:
        model = Group
        fields = ('name', 'permissions')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['users'].label_from_instance = format_user_choice
        if self.instance and self.instance.pk:
            self.fields['users'].initial = self.instance.user_set.order_by(
                'first_name', 'last_name', 'username',
            )

    def save(self, commit=True):
        group = super().save(commit=commit)
        if commit:
            self._save_users(group)
        else:
            old_save_m2m = self.save_m2m

            def save_m2m():
                old_save_m2m()
                self._save_users(group)

            self.save_m2m = save_m2m
        return group

    def _save_users(self, group):
        group.user_set.set(self.cleaned_data.get('users', []))


class GroupAdmin(BaseGroupAdmin):
    form = GroupAdminForm
    list_display = ['name', 'member_count', 'permission_count']
    search_fields = ['name', 'user__username', 'user__first_name', 'user__last_name', 'user__email']
    ordering = ['name']
    filter_horizontal = ['permissions']

    def get_queryset(self, request):
        from django.db.models import Count
        return (
            super()
            .get_queryset(request)
            .annotate(
                _member_count=Count('user', distinct=True),
                _permission_count=Count('permissions', distinct=True),
            )
        )

    @admin.display(description='Members', ordering='_member_count')
    def member_count(self, obj):
        return getattr(obj, '_member_count', obj.user_set.count())

    @admin.display(description='Permissions', ordering='_permission_count')
    def permission_count(self, obj):
        return getattr(obj, '_permission_count', obj.permissions.count())

    def _can_edit_membership(self, request):
        """Membership changes require user-change rights (not group-change alone)."""
        return request.user.is_superuser or request.user.has_perm('auth.change_user')

    def get_form(self, request, obj=None, change=False, **kwargs):
        BaseForm = super().get_form(request, obj, change, **kwargs)
        can_edit_membership = self._can_edit_membership(request)

        class BoundGroupAdminForm(BaseForm):
            def __init__(self, *args, **form_kwargs):
                super().__init__(*args, **form_kwargs)
                if not can_edit_membership and 'users' in self.fields:
                    self.fields['users'].disabled = True
                    self.fields['users'].help_text = (
                        'You can view members here, but need “Can change user” '
                        'permission to add or remove people from this group.'
                    )

            def _save_users(self, group):
                if not can_edit_membership:
                    return
                group.user_set.set(self.cleaned_data.get('users', []))

        return BoundGroupAdminForm


class UserAutocompleteJsonView(AutocompleteJsonView):
    def serialize_result(self, obj, to_field_name):
        return {
            'id': str(getattr(obj, to_field_name)),
            'text': format_user_choice(obj),
        }


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
    search_fields = ['username', 'first_name', 'last_name', 'email']
    change_list_template = 'admin/auth/user/change_list.html'

    @admin.display(description='Department')
    def department_display(self, obj):
        if hasattr(obj, 'profile'):
            return obj.profile.department or '—'
        return '—'

    def autocomplete_view(self, request):
        return UserAutocompleteJsonView.as_view(model_admin=self)(request)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'sync-ad/',
                self.admin_site.admin_view(self.sync_ad_users_view),
                name='auth_user_sync_ad',
            ),
        ]
        return custom + urls

    def sync_ad_users_view(self, request):
        """One-click AD sync from the Users list."""
        if request.method != 'POST':
            return redirect('admin:sync_ldap_users')

        result = run_ldap_sync(
            dry_run=False,
            update_existing=True,
            verbose=False,
            triggered_by=request.user,
            log_model=True,
        )
        level = messages.SUCCESS if result.success else messages.ERROR
        messages.add_message(request, level, result.message)
        if result.success:
            messages.info(
                request,
                f'LDAP entries: {result.total_ldap_entries}. '
                f'Created {result.created}, updated {result.updated}, '
                f'skipped {result.skipped}, errors {result.errors}.'
            )
        return redirect(reverse('admin:auth_user_changelist'))


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'department', 'position', 'email', 'is_active']
    search_fields = ['user__username', 'email', 'ldap_dn', 'department']
    readonly_fields = ['ldap_dn']
    filter_horizontal = ['roles']


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'level']


# Re-register User with profile inline; Group with membership picker
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.unregister(Group)
admin.site.register(Group, GroupAdmin)


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
        context['last_sync'] = LDAPSyncLog.objects.first()
    except Exception:
        context['last_sync'] = None
    return context


admin.site.each_context = _each_context_with_sync

admin.site.site_header = 'Kapa Oil Refineries — Artwork Administration'
admin.site.site_title = 'Kapa Artwork Admin'
admin.site.index_title = 'System Management'
