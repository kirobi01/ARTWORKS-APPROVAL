# scheduler_script.py
import os
import sys
import django
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import logging
from celery import shared_task

@shared_task
def generate_pdf_task():
    # Your logic to generate a PDF goes here
    pass

# Set up Django environment
sys.path.append('C:/Users/support.user5/Documents/newfolder/RMTR')  # Update path to your project
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RMTr.settings')
django.setup()

from RMTReports.models import RMTRRequest

logger = logging.getLogger(__name__)

STAGE_TIMELINES = {
    'Pending: HOD Purchase Approval': {'hours': 0.5},
    'Pending: Management 1st Approval': {'hours': 1},
    'Pending: Management 2nd Approval': {'hours': 1},
    'Pending: HOD Approval': {'hours': 1},
    'Pending: HOD Test Approval': {'hours': 1},
    'Pending: Lab Test': {'hours': None},
    'Pending: QAO Review': {'hours': 1},
    'Pending: Management Test Approval': {'hours': 1},
    'Pending: Milan Approval': {'hours': 1},
}

def is_sunday(date):
    return date.weekday() == 6

def get_business_hours_elapsed(start_date, end_date):
    if start_date > end_date:
        return 0
    
    total_hours = 0
    current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date_normalized = end_date.replace(hour=23, minute=59, second=59)
    
    while current_date <= end_date_normalized:
        if not is_sunday(current_date):
            if current_date.date() == start_date.date():
                day_hours = min(24 - start_date.hour, (end_date - start_date).seconds / 3600)
            elif current_date.date() == end_date.date():
                day_hours = end_date.hour
            else:
                day_hours = 24
            total_hours += day_hours
        current_date += timedelta(days=1)
    
    return total_hours

def get_lab_timeline(report):
    if report.status == 'Pending: Lab Test':
        if hasattr(report, 'lab_timeline_days') and report.lab_timeline_days:
            business_hours = report.lab_timeline_days * 24
            return {'hours': business_hours}
    return {'hours': 72}


def check_deadlines():
    try:
        current_time = timezone.now()
        pending_reports = RMTRRequest.objects.exclude(
            status__in=['completed', 'rejected']
        ).filter(last_status_change__isnull=False)

        for report in pending_reports:
            hours_elapsed = get_business_hours_elapsed(report.last_status_change, current_time)
            timeline_config = (STAGE_TIMELINES.get(report.status, {'hours': 1}) 
                           if report.status != 'Pending: Lab Test' 
                           else get_lab_timeline(report))
            

            if (timeline_config['hours'] and 
                hours_elapsed > timeline_config['hours'] and
                (report.last_reminder_sent is None or 
                 (current_time - report.last_reminder_sent) > timedelta(hours=24))):
                
                recipients = ['support.user5@kapa-oil.com']
                if report.current_user and report.current_user.email:
                    recipients.append(report.current_user.email)
                
                subject = f'Timeline Alert - RMTR {report.rmtr_no}'
                message = (
                    f"RMTR {report.rmtr_no} needs attention:\n\n"
                    f"Status: {report.status}\n"
                    f"Time Elapsed: {hours_elapsed:.1f} hours\n"
                    f"Expected Timeline: {timeline_config['hours']} hours\n"
                    f"Assignee: {report.current_user.get_full_name() if report.current_user else 'Unassigned'}"
                )

                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=recipients,
                    fail_silently=False
                )

                report.last_reminder_sent = current_time
                report.save(update_fields=['last_reminder_sent'])
                logger.info(f"Reminder sent for RMTR {report.rmtr_no}")

    except Exception as e:
        logger.error(f"Error in check_deadlines: {str(e)}", exc_info=True)

if __name__ == '__main__':
    check_deadlines()