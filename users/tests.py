from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from users.account_utils import deduplicate_users, get_user_for_authentication
from users.authentication import FlexibleUsernameBackend


class FlexibleUsernameBackendTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('Test.User', password='Secret123')

    def test_case_insensitive_login(self):
        backend = FlexibleUsernameBackend()
        user = backend.authenticate(None, username='test.user', password='Secret123')
        self.assertEqual(user, self.user)

    def test_wrong_password_returns_none(self):
        backend = FlexibleUsernameBackend()
        self.assertIsNone(backend.authenticate(None, username='test.user', password='wrong'))

    def test_duplicate_usernames_do_not_break_login(self):
        User = get_user_model()
        duplicate = User(username='dup@test.com', email='dup@test.com')
        duplicate.set_password('Secret123')
        duplicate.save()
        User.objects.filter(pk=duplicate.pk).update(username='Test.User')
        self.assertEqual(User.objects.filter(username__iexact='test.user').count(), 2)

        backend = FlexibleUsernameBackend()
        user = backend.authenticate(None, username='TEST.USER', password='Secret123')
        self.assertIsNotNone(user)
        self.assertEqual(User.objects.filter(username__iexact='test.user').count(), 1)

    def test_deduplicate_users_is_idempotent(self):
        User = get_user_model()
        first = User.objects.create_user('first.user', password='x')
        second = User(username='second@test.com', email='second@test.com')
        second.set_password('y')
        second.save()
        User.objects.filter(pk=second.pk).update(username='First.User')
        self.assertEqual(User.objects.filter(username__iexact='first.user').count(), 2)
        merged, _ = deduplicate_users()
        self.assertGreaterEqual(merged, 1)
        self.assertEqual(User.objects.filter(username='first.user').count(), 1)
        merged_again, _ = deduplicate_users()
        self.assertEqual(merged_again, 0)
        self.assertTrue(User.objects.filter(pk=first.pk).exists() or User.objects.filter(username='first.user').exists())

    def test_get_user_for_authentication_normalizes_username(self):
        user = get_user_for_authentication('TEST.USER')
        self.assertEqual(user.username, 'test.user')


class GroupAdminMembershipTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            'group_admin_ui', 'group_admin_ui@example.com', 'pass',
        )
        self.alice = User.objects.create_user(
            'group_alice', password='pass', first_name='Alice', last_name='A',
        )
        self.bob = User.objects.create_user(
            'group_bob', password='pass', first_name='Bob', last_name='B',
        )
        self.group, _ = Group.objects.get_or_create(name='GROUP_ADMIN_TEST')
        self.group.user_set.clear()
        self.group.user_set.add(self.alice)
        self.client = Client()
        self.client.force_login(self.admin)

    def test_group_list_shows_member_count(self):
        response = self.client.get(reverse('admin:auth_group_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'GROUP_ADMIN_TEST')
        self.assertContains(response, '>1<')

    def test_group_change_shows_current_members(self):
        response = self.client.get(reverse('admin:auth_group_change', args=[self.group.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Members')
        self.assertContains(response, 'Alice A (group_alice)')

    def test_add_and_remove_members_from_group_admin(self):
        url = reverse('admin:auth_group_change', args=[self.group.pk])
        response = self.client.post(url, {
            'name': 'GROUP_ADMIN_TEST',
            'users': [str(self.bob.pk)],
        })
        self.assertEqual(
            response.status_code,
            302,
            getattr(response, 'context', None) and response.context.get('adminform'),
        )
        members = set(self.group.user_set.values_list('username', flat=True))
        self.assertEqual(members, {'group_bob'})
        self.assertFalse(self.group.user_set.filter(pk=self.alice.pk).exists())

    def test_clear_all_members(self):
        url = reverse('admin:auth_group_change', args=[self.group.pk])
        response = self.client.post(url, {
            'name': 'GROUP_ADMIN_TEST',
            # No users selected clears membership
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.group.user_set.count(), 0)

    def test_change_group_only_cannot_alter_membership(self):
        """Staff with change_group but not change_user may view, not rewrite members."""
        from django.contrib.auth.models import Permission

        User = get_user_model()
        limited = User.objects.create_user('group_only_staff', password='pass', is_staff=True)
        limited.user_permissions.add(
            Permission.objects.get(codename='view_group', content_type__app_label='auth'),
            Permission.objects.get(codename='change_group', content_type__app_label='auth'),
        )
        client = Client()
        client.force_login(limited)
        url = reverse('admin:auth_group_change', args=[self.group.pk])
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice A (group_alice)')
        response = client.post(url, {
            'name': 'GROUP_ADMIN_TEST',
            'users': [str(self.bob.pk)],
        })
        self.assertEqual(response.status_code, 302)
        members = set(self.group.user_set.values_list('username', flat=True))
        self.assertEqual(members, {'group_alice'})
