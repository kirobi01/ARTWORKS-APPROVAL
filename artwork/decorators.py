from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def group_required(*group_names):
    """Require user to be in at least one of the specified groups."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            user_groups = set(request.user.groups.values_list('name', flat=True))
            if user_groups.intersection(set(group_names)) or 'ADMIN' in user_groups:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied(
                'You don’t have permission for this action. '
                'Please use an item assigned to your role from Pending.'
            )
        return wrapper
    return decorator


def stage_approval_required(stage_key):
    """Require user to be in the group for a specific approval stage."""
    from .config import ARTWORK_STATUS_CONFIG
    cfg = ARTWORK_STATUS_CONFIG.get(stage_key, {})
    group = cfg.get('group', '')
    return group_required(group, 'ADMIN')
