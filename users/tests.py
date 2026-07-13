from django.contrib.auth import get_user_model
from django.test import TestCase

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
