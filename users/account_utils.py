"""Username normalization and duplicate account handling."""
import logging
from collections import defaultdict

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

logger = logging.getLogger('users')


def normalize_username(username):
    return (username or '').strip().lower()


def find_users_by_username(username):
    User = get_user_model()
    normalized = normalize_username(username)
    if not normalized:
        return User.objects.none()
    return User.objects.filter(username__iexact=normalized).order_by('pk')


def find_users_by_login_id(login_id):
    """Match username, Django email, or profile email (case-insensitive)."""
    User = get_user_model()
    normalized = normalize_username(login_id)
    if not normalized:
        return User.objects.none()
    return User.objects.filter(
        Q(username__iexact=normalized)
        | Q(email__iexact=normalized)
        | Q(profile__email__iexact=normalized)
    ).distinct().order_by('pk')


def pick_canonical_user(users):
    """Choose the account to keep when multiple usernames match case-insensitively."""
    users = list(users)
    if not users:
        return None
    if len(users) == 1:
        return users[0]

    def score(user):
        profile = getattr(user, 'profile', None)
        ldap_dn = getattr(profile, 'ldap_dn', '') if profile else ''
        return (
            1 if ldap_dn else 0,
            1 if user.is_superuser else 0,
            1 if user.is_staff else 0,
            1 if user.last_login else 0,
            -user.pk,
        )

    return max(users, key=score)


def reassign_user_references(from_user, to_user):
    """Point all foreign keys and group memberships at the canonical user."""
    User = get_user_model()
    if from_user.pk == to_user.pk:
        return

    for model in apps.get_models():
        if model is User:
            continue
        for field in model._meta.get_fields():
            if not getattr(field, 'many_to_one', False):
                continue
            if getattr(field, 'related_model', None) is not User:
                continue
            if not field.concrete:
                continue
            model.objects.filter(**{field.name: from_user}).update(**{field.name: to_user})

        for field in model._meta.get_fields():
            if not getattr(field, 'many_to_many', False):
                continue
            if getattr(field, 'related_model', None) is not User:
                continue
            if field.auto_created:
                continue
            through = getattr(field, 'through', None)
            if through is None:
                continue
            for m2m_field in through._meta.get_fields():
                if getattr(m2m_field, 'many_to_one', False) and m2m_field.related_model is User:
                    through.objects.filter(**{m2m_field.name: from_user}).update(
                        **{m2m_field.name: to_user}
                    )

    to_user.groups.add(*from_user.groups.all())
    to_user.user_permissions.add(*from_user.user_permissions.all())


def merge_profile_data(canonical, duplicate):
    try:
        canonical_profile = canonical.profile
    except Exception:
        from users.models import Profile
        canonical_profile, _ = Profile.objects.get_or_create(user=canonical)

    try:
        duplicate_profile = duplicate.profile
    except Exception:
        return

    if not canonical_profile.ldap_dn and duplicate_profile.ldap_dn:
        canonical_profile.ldap_dn = duplicate_profile.ldap_dn
    if not canonical_profile.email and duplicate_profile.email:
        canonical_profile.email = duplicate_profile.email
    if not canonical_profile.position and duplicate_profile.position:
        canonical_profile.position = duplicate_profile.position
    if not canonical_profile.extension_no and duplicate_profile.extension_no:
        canonical_profile.extension_no = duplicate_profile.extension_no
    if not canonical_profile.department and duplicate_profile.department:
        canonical_profile.department = duplicate_profile.department
    canonical_profile.roles.add(*duplicate_profile.roles.all())
    canonical_profile.save()


def deduplicate_users(*, dry_run=False):
    """
    Merge case-insensitive username duplicates and normalize usernames to lowercase.
    Returns (merged_groups, normalized_count).
    """
    User = get_user_model()
    grouped = defaultdict(list)
    for user in User.objects.all().order_by('pk'):
        grouped[normalize_username(user.username)].append(user)

    merged_groups = 0
    normalized_count = 0

    with transaction.atomic():
        for normalized, users in grouped.items():
            if not normalized:
                continue

            canonical = pick_canonical_user(users)
            duplicates = [user for user in users if user.pk != canonical.pk]

            if duplicates:
                merged_groups += 1
                duplicate_ids = [user.pk for user in duplicates]
                logger.warning(
                    'Merging duplicate users for %r: keeping pk=%s, removing %s',
                    normalized, canonical.pk, duplicate_ids,
                )
                if not dry_run:
                    for duplicate in duplicates:
                        merge_profile_data(canonical, duplicate)
                        reassign_user_references(duplicate, canonical)
                        duplicate.delete()

            if canonical.username != normalized:
                normalized_count += 1
                if not dry_run:
                    canonical.username = normalized
                    canonical.save(update_fields=['username'])

        if dry_run:
            transaction.set_rollback(True)

    return merged_groups, normalized_count


def get_user_for_authentication(username):
    """
    Resolve a single user for login by username or email.
    Deduplicates on the fly if duplicates exist.
    Never raises MultipleObjectsReturned.
    """
    users = list(find_users_by_login_id(username))
    if not users:
        return None
    if len(users) == 1:
        return users[0]

    canonical = pick_canonical_user(users)
    logger.warning(
        'Duplicate users detected for %r during login; merging into pk=%s',
        username, canonical.pk,
    )
    deduplicate_users()
    return get_user_model().objects.filter(pk=canonical.pk).first()
