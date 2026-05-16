# users/permissions.py

from functools import wraps
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
import logging

# Set up logger
logger = logging.getLogger(__name__)

# Define all possible statuses and roles for validation
VALID_STATUSES = {
    'pending',
    'hod_purchase_approved',
    'management_approved',
    'fm_approved',
    'hod_approved',
    'test_completed',
    'qao_reviewed',
    'hod_test_approved',
    'fm_test_approved',
    'management_test_approved'
}

VALID_ROLES = {
    'HOD_PURCHASE',
    'MANAGEMENT',
    'FM',
    'HOD',
    'LAB',
    'QAO',
    'HOD_TEST',
    'MANAGEMENT_TEST',
    'FM_TEST',
    'MILAN'
    
}

# Status-based permissions with documentation
STATUS_ROLE_MAPPING = {
    'pending': ['HOD_PURCHASE'], 
    'hod_purchase_approved': ['MANAGEMENT'], 
    'management_approved': ['FM'],  
    'fm_approved': ['HOD'], 
    'hod_approved': ['LAB'], 
    'test_completed': ['QAO'],  
    'qao_reviewed': ['HOD'], 
    'hod_test_approved': ['FM'],
    'fm_test_approved': ['MANAGEMENT'], 
    'management_test_approved': ['MILAN'] 
}

def role_required(role_codes):
    """
    Decorator to check if user has required role(s)
    
    Args:
        role_codes (str|list): Required role code(s) for access
    
    Returns:
        function: Decorated view function
    
    Usage:
        @role_required(['HOD_PURCHASE', 'MANAGEMENT'])
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            try:
                # Check authentication
                if not request.user.is_authenticated:
                    logger.warning(f"Unauthenticated access attempt to {view_func.__name__}")
                    return JsonResponse({
                        'error': 'Authentication required',
                        'detail': 'Please log in to access this resource'
                    }, status=401)
                
                # Check profile exists
                if not hasattr(request.user, 'profile'):
                    logger.error(f"No profile found for user {request.user.username}")
                    return JsonResponse({
                        'error': 'User profile not found',
                        'detail': 'Please contact system administrator'
                    }, status=403)
                
                # Normalize role_codes to list
                required_roles = [role_codes] if isinstance(role_codes, str) else role_codes
                
                # Validate required roles
                invalid_roles = set(required_roles) - VALID_ROLES
                if invalid_roles:
                    logger.error(f"Invalid roles specified in decorator: {invalid_roles}")
                    return JsonResponse({
                        'error': 'Invalid role configuration',
                        'detail': 'System configuration error'
                    }, status=500)
                
                # Check user roles
                user_roles = set(request.user.profile.roles.values_list('code', flat=True))
                has_required_role = bool(user_roles & set(required_roles))
                
                if not has_required_role:
                    logger.warning(
                        f"Access denied for user {request.user.username}. "
                        f"Required roles: {required_roles}, User roles: {user_roles}"
                    )
                    raise PermissionDenied('Insufficient permissions')
                
                return view_func(request, *args, **kwargs)
                
            except PermissionDenied as e:
                return JsonResponse({
                    'error': str(e),
                    'detail': 'You do not have the required permissions'
                }, status=403)
                
            except Exception as e:
                logger.error(f"Unexpected error in role_required: {str(e)}")
                return JsonResponse({
                    'error': 'Internal server error',
                    'detail': 'An unexpected error occurred'
                }, status=500)
                
        return _wrapped_view
    return decorator

def can_access_rmtr(user, rmtr_status):
    """
    Check if user can access RMTR based on its status
    
    Args:
        user: User object
        rmtr_status (str): Current status of the RMTR
    
    Returns:
        bool: True if user can access RMTR, False otherwise
    """
    try:
        # Basic validation
        if not user.is_authenticated or not hasattr(user, 'profile'):
            logger.warning(f"Access attempt without auth/profile: {user}")
            return False
        
        # Validate status
        if rmtr_status not in VALID_STATUSES:
            logger.error(f"Invalid RMTR status encountered: {rmtr_status}")
            return False
        
        # Get allowed roles for status
        allowed_roles = set(STATUS_ROLE_MAPPING.get(rmtr_status, []))
        if not allowed_roles:
            logger.warning(f"No roles configured for status: {rmtr_status}")
            return False
        
        # Check user roles
        user_roles = set(user.profile.roles.values_list('code', flat=True))
        has_access = bool(user_roles & allowed_roles)
        
        # Log access attempts
        if not has_access:
            logger.warning(
                f"Access denied for user {user.username} to RMTR with status {rmtr_status}. "
                f"User roles: {user_roles}, Required roles: {allowed_roles}"
            )
        
        return has_access
        
    except Exception as e:
        logger.error(f"Error in can_access_rmtr: {str(e)}")
        return False

def get_next_approvers(current_status):
    """
    Get the roles that can approve the next step based on current status
    
    Args:
        current_status (str): Current RMTR status
    
    Returns:
        list: List of role codes that can approve the next step
    """
    try:
        return STATUS_ROLE_MAPPING.get(current_status, [])
    except Exception as e:
        logger.error(f"Error getting next approvers for status {current_status}: {str(e)}")
        return []