# views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from .permissions import role_required, can_access_rmtr
from .models import Profile, Role, RMTR  # Assuming RMTR model exists
import logging
from django.http import Http404
# Set up logging
logger = logging.getLogger(__name__)

def rmtr_to_dict(rmtr):
    """
    Convert RMTR object to dictionary for JSON response
    
    Args:
        rmtr: RMTR model instance
    Returns:
        dict: Serialized RMTR data
    """
    return {
        'id': rmtr.id,
        'rmtr_no': rmtr.rmtr_no,
        'status': rmtr.status,
        'created_at': rmtr.created_at.isoformat() if hasattr(rmtr, 'created_at') else None,
        # Add other relevant fields
    }

def get_rmtr_by_no(rmtr_no):
    """
    Retrieve RMTR by its number
    
    Args:
        rmtr_no: RMTR number to look up
    Returns:
        RMTR: Retrieved RMTR object
    Raises:
        Http404: If RMTR not found
    """
    try:
        return get_object_or_404(RMTR, rmtr_no=rmtr_no)
    except ValueError:
        raise Http404(f"Invalid RMTR number format: {rmtr_no}")

@login_required
def user_profile(request):
    """
    Display user profile with roles
    """
    try:
        if not hasattr(request.user, 'profile'):
            # Create profile if it doesn't exist
            Profile.objects.create(user=request.user)
        
        context = {
            'user_roles': request.user.profile.roles.all(),
            'user_profile': request.user.profile
        }
        return render(request, 'users/profile.html', context)
    
    except Exception as e:
        logger.error(f"Error in user_profile view: {str(e)}")
        return render(request, 'users/profile.html', {
            'error': 'Error loading profile data'
        })

@login_required
@role_required(['HOD_PURCHASE', 'MANAGEMENT', 'FM', 'HOD', 'QAO', 'MILAN'])
def rmtr_access(request, rmtr_no):
    """
    Handle RMTR access requests
    
    Args:
        request: HTTP request object
        rmtr_no: RMTR number to access
    Returns:
        JsonResponse: RMTR data if access granted
    """
    try:
        # Validate input
        if not rmtr_no:
            return JsonResponse({
                'error': 'RMTR number is required'
            }, status=400)

        # Get RMTR
        try:
            rmtr = get_rmtr_by_no(rmtr_no)
        except Http404:
            return JsonResponse({
                'error': f'RMTR {rmtr_no} not found'
            }, status=404)

        # Check user profile exists
        if not hasattr(request.user, 'profile'):
            Profile.objects.create(user=request.user)
            logger.warning(f"Created missing profile for user {request.user.username}")

        # Check permissions
        if not can_access_rmtr(request.user, rmtr.status):
            logger.warning(
                f"Access denied for user {request.user.username} "
                f"to RMTR {rmtr_no} with status {rmtr.status}"
            )
            return JsonResponse({
                'error': 'You do not have permission to access this RMTR',
                'status': rmtr.status,
                'user_roles': list(request.user.profile.roles.values_list('code', flat=True))
            }, status=403)

        # Return RMTR data
        return JsonResponse({
            'rmtr': rmtr_to_dict(rmtr),
            'user_roles': list(request.user.profile.roles.values_list('code', flat=True))
        })

    except Exception as e:
        logger.error(f"Error in rmtr_access view: {str(e)}")
        return JsonResponse({
            'error': 'Internal server error occurred'
        }, status=500)