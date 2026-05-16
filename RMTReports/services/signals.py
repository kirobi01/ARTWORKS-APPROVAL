
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from RMTReports.services.notification_service import NotificationService
from RMTReports.services.status_service import RMTRStatusManager
from RMTReports.config.notification_config import APPROVAL_CONFIG, STATUS_FLOW
import logging

from RMTReports.models import (
    RMTRRequest, 
    HODPurchaseApproval, 
    ManagementApproval, 
    FMApproval,
    HODApproval, 
    TestResults, 
    QAOTestApproval, 
    HODTestApproval,
    FMTestApproval, 
    ManagementTestApproval, 
    MilanTestApproval
)

logger = logging.getLogger(__name__)

def get_next_stage(current_stage):
    """Helper function to get the next stage based on config"""
    stage_order = [
        'HODPurchaseApproval',
        'ManagementApproval',
        'FMApproval',
        'HODApproval',
        'TestResults',
        'QAOTestApproval',
        'HODTestApproval',
        'FMTestApproval',
        'ManagementTestApproval',
        'MilanTestApproval'
    ]
    try:
        current_index = stage_order.index(current_stage)
        if current_index < len(stage_order) - 1:
            return stage_order[current_index + 1]
        return None
    except ValueError:
        return None

# Rest of your signal code stays the same...

@receiver(post_save, sender=HODPurchaseApproval)
@receiver(post_save, sender=ManagementApproval)
@receiver(post_save, sender=FMApproval)
@receiver(post_save, sender=HODApproval)
@receiver(post_save, sender=TestResults)
@receiver(post_save, sender=QAOTestApproval)
@receiver(post_save, sender=HODTestApproval)
@receiver(post_save, sender=FMTestApproval)
@receiver(post_save, sender=ManagementTestApproval)
@receiver(post_save, sender=MilanTestApproval)
def handle_approval(sender, instance, created, **kwargs):
    """Handle approval status changes and notifications"""
    if created:
        return  # Skip if just created

    try:
        stage_name = sender.__name__
        logger.info(f"Processing {stage_name} for RMTR #{instance.request.rmtr_no}")

        if not hasattr(instance, 'request'):
            logger.error(f"Instance {instance} has no request attribute")
            return

        request = instance.request

        # Handle approval
        if hasattr(instance, 'approved') and instance.approved:
            logger.info(f"Processing approval for {stage_name}")
            
            # Get comments field dynamically
            comments_field = f"{stage_name.lower()}_comments"
            comments = getattr(instance, comments_field, '') if hasattr(instance, comments_field) else ''

            # Send notification
            NotificationService.send_approval_notification(
                request=request,
                stage_name=stage_name,
                is_approved=True,
                comments=comments
            )

            # Update status
            next_stage = get_next_stage(stage_name)
            if next_stage:
                new_status = f"pending_{next_stage.lower()}"
                logger.info(f"Updating status to: {new_status}")
                request.status = new_status
            else:
                logger.info("Setting status to completed")
                request.status = 'completed'
            request.save()

        # Handle rejection
        elif hasattr(instance, 'rejected') and instance.rejected:
            logger.info(f"Processing rejection for {stage_name}")
            
            # Get comments field dynamically
            comments_field = f"{stage_name.lower()}_comments"
            comments = getattr(instance, comments_field, '') if hasattr(instance, comments_field) else ''

            # Send notification
            NotificationService.send_approval_notification(
                request=request,
                stage_name=stage_name,
                is_approved=False,
                comments=comments
            )

            # Update status
            logger.info("Setting status to rejected")
            request.status = 'rejected'
            request.save()

    except Exception as e:
        logger.error(f"Error in approval handler: {str(e)}", exc_info=True)
        raise

# Optional: Add signal for RMTRRequest creation
@receiver(post_save, sender=RMTRRequest)
def handle_rmtr_creation(sender, instance, created, **kwargs):
    """Handle initial RMTR request creation"""
    if created:
        try:
            logger.info(f"New RMTR request created: #{instance.rmtr_no}")
            NotificationService.send_approval_notification(
                request=instance,
                stage_name='RMTRRequest',
                is_approved=True,
                comments='New RMTR request created'
            )
        except Exception as e:
            logger.error(f"Error handling RMTR creation: {str(e)}", exc_info=True)
            raise