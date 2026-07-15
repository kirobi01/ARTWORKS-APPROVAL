import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

logger = logging.getLogger('users')

from users.account_utils import get_user_for_authentication, normalize_username
from users.ldap_client import authenticate_ad_user, decode_ldap_attrs, ldap_is_available


class FlexibleUsernameBackend(ModelBackend):
    """Case-insensitive username or email lookup for local Django accounts."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(get_user_model().USERNAME_FIELD)
        if not username or not password:
            return None
        user = get_user_for_authentication(username)
        if user is None:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None


class LDAPAuthenticationBackend:
    """Authenticate users against Active Directory using their AD password."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        from django.conf import settings

        if not getattr(settings, 'LDAP_ENABLED', False):
            return None

        if not ldap_is_available():
            logger.error('LDAP is enabled but ldap3/python-ldap is not installed')
            return None

        login_id = normalize_username(username)
        user_dn, attrs = authenticate_ad_user(login_id, password)
        if not user_dn:
            return None

        return self._get_or_create_user(login_id, user_dn, attrs)

    def _get_or_create_user(self, login_id, ldap_dn, attrs):
        from users.models import Profile

        User = get_user_model()
        sam = normalize_username(decode_ldap_attrs(attrs, 'sAMAccountName'))
        if not sam:
            sam = login_id.split('@', 1)[0] if '@' in login_id else login_id
            sam = normalize_username(sam)

        email = decode_ldap_attrs(attrs, 'mail') or (
            login_id if '@' in login_id else f'{sam}@kapa-oil.local'
        )
        email = normalize_username(email)
        first_name = decode_ldap_attrs(attrs, 'givenName')
        last_name = decode_ldap_attrs(attrs, 'sn')
        position = decode_ldap_attrs(attrs, 'title')
        phone = decode_ldap_attrs(attrs, 'telephoneNumber')
        display_name = decode_ldap_attrs(attrs, 'displayName')

        if not first_name and display_name:
            parts = display_name.split()
            first_name = parts[0]
            last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''

        user = User.objects.filter(
            Q(username__iexact=sam)
            | Q(profile__ldap_dn=ldap_dn)
            | Q(email__iexact=email)
            | Q(profile__email__iexact=email)
            | Q(email__iexact=login_id)
            | Q(profile__email__iexact=login_id)
        ).order_by('pk').first()

        if user:
            # Keep AD sAMAccountName as canonical username; never overwrite with email.
            if user.username.lower() != sam:
                user.username = sam
            user.email = email
            user.first_name = first_name or sam
            user.last_name = last_name or ''
            user.is_active = True
            user.set_unusable_password()
            user.save()
        else:
            user = User.objects.create(
                username=sam,
                email=email,
                first_name=first_name or sam,
                last_name=last_name or '',
                is_active=True,
            )
            user.set_unusable_password()
            user.save()

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.email = email
        profile.ldap_dn = ldap_dn
        profile.position = position
        profile.extension_no = phone
        profile.is_active = True
        profile.save()

        return user if self._user_can_authenticate(user) else None

    def _user_can_authenticate(self, user):
        return getattr(user, 'is_active', True)

    def get_user(self, user_id):
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
