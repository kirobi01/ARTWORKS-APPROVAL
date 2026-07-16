"""Route Operations HOD approval and alerts by product category."""
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .config import ARTWORK_STATUS_CONFIG
from .models import ProductCategory


OPS_STAGE_KEY = 'operations_hod'
OPS_STATUS = ARTWORK_STATUS_CONFIG[OPS_STAGE_KEY]['db_status']
OPS_DENIED_MESSAGE = (
    'This artwork belongs to another department. '
    'Only that department’s Operations HOD or Deputy can review it.'
)


def get_category_for_artwork(artwork):
    """
    Resolve category for routing.

    Prefer the active category; if none, still use an inactive match so
    deactivating a category cannot reopen mapped work to all Ops HODs.
    """
    name = getattr(artwork, 'product_category', '') or ''
    category = ProductCategory.get_by_name(name, active_only=True)
    if category:
        return category
    return ProductCategory.get_by_name(name, active_only=False)


def category_has_operations_mapping(artwork):
    """
    True when the artwork's category exists and has HOD and/or Deputy set.

    Uses FK presence (not active-user filtering) so an inactive mapped user
    never opens the item to the whole OPERATIONS_HOD group.
    """
    category = get_category_for_artwork(artwork)
    if not category:
        return False
    return bool(category.hod_id or category.deputy_hod_id)


def get_operations_assignees(artwork):
    """
    Return active HOD/deputy users assigned to this artwork's product category.

    Empty list with category_has_operations_mapping=True means mapped but no
    active assignees — callers must NOT fall back to the full group.
    """
    category = get_category_for_artwork(artwork)
    if not category:
        return []
    return category.operations_assignees()


def user_is_operations_assignee(user, artwork):
    if not user or not user.is_active:
        return False
    return any(assignee.pk == user.pk for assignee in get_operations_assignees(artwork))


def user_can_approve_operations(user, artwork):
    """
    Admin/superuser always can.

    If the category has HOD/deputy mapped, ONLY those users may approve/reject.
    If unmapped, any OPERATIONS_HOD group member may approve (legacy fallback).
    """
    if not user or not user.is_active:
        return False
    if user.is_superuser:
        return True
    groups = set(user.groups.values_list('name', flat=True))
    if 'ADMIN' in groups:
        return True
    if 'OPERATIONS_HOD' not in groups:
        return False

    if category_has_operations_mapping(artwork):
        return user_is_operations_assignee(user, artwork)

    # No HOD/Deputy mapped on this category yet
    return True


def assert_user_can_approve_operations(user, artwork):
    """Raise PermissionDenied when a cross-department Operations action is attempted."""
    if not user_can_approve_operations(user, artwork):
        raise PermissionDenied(OPS_DENIED_MESSAGE)


def category_names_for_operations_user(user):
    """Active category names where the user is HOD or deputy."""
    if not user:
        return []
    return list(
        ProductCategory.objects.filter(
            is_active=True,
        ).filter(
            Q(hod=user) | Q(deputy_hod=user),
        ).values_list('name', flat=True)
    )


def mapped_category_names():
    """
    Names of categories (active or inactive) that have HOD and/or Deputy assigned.

    Inactive categories remain "mapped" so pending Ops items stay locked.
    """
    return list(
        ProductCategory.objects.filter(
            Q(hod__isnull=False) | Q(deputy_hod__isnull=False),
        ).values_list('name', flat=True)
    )


def filter_operations_pending_queryset(queryset, user):
    """
    Restrict Operations-pending rows to categories assigned to this user.

    Mapped categories are never shown to HODs from other departments.
    Unmapped categories remain visible to all OPERATIONS_HOD users.
    A user's own submissions are always kept (matches _can_view for creators).
    """
    if not user or user.is_superuser:
        return queryset
    groups = set(user.groups.values_list('name', flat=True))
    if 'ADMIN' in groups:
        return queryset
    if 'OPERATIONS_HOD' not in groups:
        return queryset

    assigned_names = category_names_for_operations_user(user)
    mapped_names = mapped_category_names()

    ops_rows = Q(status=OPS_STATUS)
    non_ops = ~ops_rows

    allowed_ops = Q(pk__in=[])
    if assigned_names:
        name_q = Q()
        for name in assigned_names:
            name_q |= Q(product_category__iexact=name)
        allowed_ops |= name_q

    if mapped_names:
        mapped_q = Q()
        for name in mapped_names:
            mapped_q |= Q(product_category__iexact=name)
        unmapped = ~mapped_q | Q(product_category='') | Q(product_category__isnull=True)
    else:
        unmapped = Q()

    allowed_ops |= unmapped
    # Keep creator visibility aligned with _can_view (never hide own records).
    return queryset.filter(Q(created_by=user) | non_ops | (ops_rows & allowed_ops))
