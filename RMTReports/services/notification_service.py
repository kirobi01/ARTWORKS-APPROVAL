from django.utils import timezone
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import send_mail
import logging
from ..config.notification_config import APPROVAL_CONFIG, EMAIL_CONFIG, DEFAULT_CC

logger = logging.getLogger(__name__)

class NotificationService:
    @staticmethod
    def send_approval_notification(request, stage_name, is_approved, comments):
        try:
            from ..config.notification_config import APPROVAL_CONFIG, EMAIL_CONFIG, DEFAULT_CC

            stage_config = APPROVAL_CONFIG.get(stage_name)
            if not stage_config:
                logger.error(f"No configuration found for stage: {stage_name}")
                return False

            status_type = 'approved' if is_approved else 'rejected'
            email_config = stage_config['recipients'][status_type]
            
            # Get recipients
            to_list = [
                email.replace('creator_email', request.requested_by.email) 
                for email in email_config['to']
            ]
            
            # Combine CC list with default CC recipients
            cc_list = list(set(
                DEFAULT_CC + 
                [email.replace('creator_email', request.requested_by.email) 
                 for email in email_config.get('cc', [])]
            ))

            # Create template context
            context = {
                'request': request,
                'comments': comments,
                'template_name': f"{stage_name.lower()}_{'approval' if is_approved else 'rejection'}",
                'date': timezone.now(),
                'stage_config': stage_config
            }

            try:
                # Render email template
                html_content = render_to_string('emails/rmtr_notifications.html', context)
                text_content = strip_tags(html_content)
            except Exception as template_error:
                logger.error(f"Template rendering error: {str(template_error)}")
                return False

            try:
                # Send email
                send_mail(
                    subject=email_config['subject'].format(rmtr_no=request.rmtr_no),
                    message=text_content,
                    html_message=html_content,
                    from_email=EMAIL_CONFIG['default_sender'],
                    recipient_list=to_list,
                    cc=cc_list,
                    fail_silently=False
                )
                
                # Log successful notification
                logger.info(
                    f"Notification sent for RMTR #{request.rmtr_no} - {stage_name}\n"
                    f"To: {to_list}\n"
                    f"CC: {cc_list}"
                )
                return True

            except Exception as email_error:
                logger.error(f"Email sending error: {str(email_error)}")
                return False

        except Exception as e:
            logger.error(f"Notification service error: {str(e)}")
            return False

    @staticmethod
    def send_error_notification(error_message, context=None):
        """Send error notification to system administrators"""
        try:
            admin_emails = ['support.user5@kapa-oil.com']
            
            subject = f"RMTR System Error - {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            message = f"""
            RMTR System Error Notification
           
            Error: {error_message}
            Time: {timezone.now()}
           
            Context:
            {context if context else 'No additional context provided'}
           """
           
            send_mail(
               subject=subject,
               message=message,
               from_email=EMAIL_CONFIG['default_sender'],
               recipient_list=admin_emails,
               fail_silently=True
           )
           
            logger.error(f"System error notification sent: {error_message}")
           
        except Exception as e:
           logger.error(f"Failed to send error notification: {str(e)}")
           
    
    @staticmethod
    def validate_email_addresses(email_list):
       """Validate email addresses before sending"""
       from django.core.validators import validate_email
       from django.core.exceptions import ValidationError
       
       valid_emails = []
       for email in email_list:
           try:
               validate_email(email)
               valid_emails.append(email)
           except ValidationError:
               logger.warning(f"Invalid email address: {email}")
               continue
       return valid_emails