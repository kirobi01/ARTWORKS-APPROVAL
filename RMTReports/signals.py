"""# signals.py
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils.html import strip_tags
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

# Enhanced Status and Email Mapping
APPROVAL_CONFIG = {
    'HODPurchaseApproval': {
        'display': 'HOD Purchase Review',
        'recipients': {
            'approved': {
                'to': ['management@kapa-oil.com'],
                'cc': ['creator_email', 'purchase.user2@kapa-oil.com'],
                'subject': 'RMTR {rmtr_no} - Approved by HOD Purchase, Pending Management Review',
                'template': 'emails/hod_purchase_approval.html'
            },
            'rejected': {
                'to': ['creator_email'],
                'cc': ['purchase.user2@kapa-oil.com'],
                'subject': 'RMTR {rmtr_no} - Rejected by HOD Purchase',
                'template': 'emails/hod_purchase_rejection.html'
            }
        }
    },
    'ManagementApproval': {
        'display': 'Management Review',
        'recipients': {
            'approved': {
                'to': ['fm@kapa-oil.com'],
                'cc': ['hod_purchase@kapa-oil.com', 'creator_email', 'purchase.user2@kapa-oil.com'],
                'subject': 'RMTR {rmtr_no} - Approved by Management, Pending FM Review',
                'template': 'emails/management_approval.html'
            },
            'rejected': {
                'to': ['creator_email', 'hod_purchase@kapa-oil.com'],
                'cc': ['purchase.user2@kapa-oil.com'],
                'subject': 'RMTR {rmtr_no} - Rejected by Management',
                'template': 'emails/management_rejection.html'
            }
        }
    },
    # Add similar configurations for other stages...
}

def send_stage_notification(request, stage_name, is_approved, comments=None):
    
    #Send stage-specific notification emails
    
    try:
        # Get stage configuration
        stage_config = APPROVAL_CONFIG.get(stage_name)
        if not stage_config:
            logger.error(f"No configuration found for stage: {stage_name}")
            return

        # Get email configuration based on approval status
        email_config = stage_config['recipients']['approved' if is_approved else 'rejected']

        # Replace placeholder values in recipient lists
        to_list = [email.replace('creator_email', request.requested_by.email) 
                  for email in email_config['to']]
        cc_list = [email.replace('creator_email', request.requested_by.email) 
                  for email in email_config['cc']]

        # Prepare email context
        context = {
            'request': request,
            'stage': stage_config['display'],
            'comments': comments,
            'timestamp': timezone.now(),
            'is_approved': is_approved,
            'material_type': request.material_type,
            'supplier': request.supplier,
            'justification': request.justification,
            'tests': request.tests,
            # Add any other relevant context
        }

        # Render email template
        html_content = render_to_string(email_config['template'], context)
        text_content = strip_tags(html_content)

        # Create email subject with replaced placeholders
        subject = email_config['subject'].format(rmtr_no=request.rmtr_no)

        # Create and send email
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to_list,
            cc=cc_list
        )
        msg.attach_alternative(html_content, "text/html")

        # Attach files if present
        if hasattr(request, 'test_image') and request.test_image:
            msg.attach_file(request.test_image.path)

        msg.send()
        logger.info(f"Email sent for RMTR #{request.rmtr_no} - {stage_name} - {'Approved' if is_approved else 'Rejected'}")

    except Exception as e:
        logger.error(f"Failed to send email notification: {str(e)}")
        raise

@receiver(post_save)
def handle_approval(sender, instance, created, **kwargs):
  #Main signal handler for all approval stages
    # Check if this is an approval model
    if not any(approval_type in sender.__name__ for approval_type in APPROVAL_CONFIG.keys()):
        return

    if created:
        return  # Skip if just created

    try:
        stage_name = sender.__name__
        request = instance.request  # Assuming all approval models have a request field

        if hasattr(instance, 'approved') and instance.approved:
            # Handle approval
            comments = getattr(instance, f'{stage_name.lower()}_comments', '')
            send_stage_notification(request, stage_name, True, comments)
            
            # Update request status
            next_stage = get_next_stage(stage_name)
            if next_stage:
                request.status = f"pending_{next_stage.lower()}"
            else:
                request.status = 'completed'
            request.save()

        elif hasattr(instance, 'rejected') and instance.rejected:
            # Handle rejection
            comments = getattr(instance, f'{stage_name.lower()}_comments', '')
            send_stage_notification(request, stage_name, False, comments)
            request.status = 'rejected'
            request.save()

    except Exception as e:
        logger.error(f"Error in approval handler: {str(e)}")
        raise
"""
# Example email template for HOD Purchase Approval:
"""
<!-- templates/emails/hod_purchase_approval.html -->
<!DOCTYPE html>
<html>
<head>
    <style>
        .header { color: #333; }
        .details { margin: 20px 0; }
        .approval-info { background: #f9f9f9; padding: 15px; }
    </style>
</head>
<body>
    <h2 class="header">RMTR Approval Notification</h2>
    <div class="details">
        <p>RMTR Request #{{ request.rmtr_no }} has been approved by HOD Purchase.</p>
        <p>The request is now pending Management review.</p>
    </div>
    <div class="approval-info">
        <h3>Request Details:</h3>
        <p>Supplier: {{ supplier }}</p>
        <p>Material Type: {{ material_type }}</p>
        <p>Tests Required: {{ tests }}</p>
        <p>Justification: {{ justification }}</p>
        {% if comments %}
        <p>Comments: {{ comments }}</p>
        {% endif %}
    </div>
    <p>Please review the request at your earliest convenience.</p>
</body>
</html>
"""