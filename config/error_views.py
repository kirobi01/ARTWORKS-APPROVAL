"""Project-level error handlers with friendly UI messages."""
from django.http import JsonResponse
from django.shortcuts import render


def _wants_json(request):
    accept = (request.headers.get('Accept') or '').lower()
    requested_with = (request.headers.get('X-Requested-With') or '').lower()
    content_type = (request.headers.get('Content-Type') or '').lower()
    if 'application/json' in accept:
        return True
    if requested_with == 'xmlhttprequest':
        return True
    # Approval actions use fetch() with FormData
    if request.method == 'POST' and 'multipart/form-data' in content_type:
        return True
    if request.method == 'POST' and request.headers.get('X-CSRFToken'):
        return True
    return False


def _friendly_403_copy(exception):
    raw = str(exception).strip() if exception else ''
    department_markers = (
        'another department',
        'mapped operations',
        'operations hod or deputy',
    )
    if any(marker in raw.lower() for marker in department_markers):
        return (
            'Wrong department',
            'This artwork belongs to another department. '
            'Only that department’s Operations HOD or Deputy can review it. '
            'Please open an item from your own Pending list.',
        )
    if 'not pending' in raw.lower() or 'not at your approval stage' in raw.lower():
        return (
            'Not ready for your review',
            'This artwork is not waiting at your approval stage right now. '
            'It may have already been actioned or moved on.',
        )
    if raw and raw.lower() not in {
        'forbidden',
        'permission denied',
        'you do not have permission to access this page.',
    }:
        return ('Access limited', raw)
    return (
        'Access limited',
        'You don’t have permission to view or action this item. '
        'If you believe this is a mistake, contact your administrator.',
    )


def permission_denied_view(request, exception=None):
    heading, message = _friendly_403_copy(exception)
    if _wants_json(request):
        return JsonResponse(
            {
                'success': False,
                'message': message,
                'heading': heading,
                'redirect': '/artwork/pending/',
            },
            status=403,
        )
    return render(
        request,
        'artwork/403.html',
        {
            'heading': heading,
            'message': message,
        },
        status=403,
    )
