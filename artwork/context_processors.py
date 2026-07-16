def _user_initials(name):
    """First letters of first two name parts, or first two chars of username."""
    parts = [p for p in (name or '').split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if parts:
        return parts[0][:2].upper()
    return '?'


def artwork_nav(request):
    """Global template context for navigation and user info."""
    if not request.user.is_authenticated:
        return {}
    groups = set(request.user.groups.values_list('name', flat=True))
    display_name = request.user.get_full_name() or request.user.username
    can_create = (
        request.user.is_superuser
        or bool(groups.intersection({'DESIGN', 'ADMIN'}))
    )
    return {
        'nav_user_groups': groups,
        'nav_is_admin': request.user.is_superuser or 'ADMIN' in groups,
        'nav_is_design': 'DESIGN' in groups or request.user.is_superuser,
        'nav_can_create': can_create,
        'nav_can_procurement': (
            request.user.is_superuser
            or bool(groups.intersection({'PROCUREMENT', 'ADMIN'}))
        ),
        'nav_display_name': display_name,
        'nav_initials': _user_initials(display_name),
        'nav_department': getattr(getattr(request.user, 'profile', None), 'department', '') or '',
    }
