import logging
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .config import ARTWORK_STATUS_CONFIG, STAGE_ORDER
from .models import ArtworkApprovalLog, ArtworkRequest
from .operations_routing import (
    assert_user_can_approve_operations,
    category_has_operations_mapping,
    get_operations_assignees,
)
from .utils import get_user_email

logger = logging.getLogger('artwork')


class ArtworkStatusManager:
    @staticmethod
    def get_stage_for_status(status):
        for key, cfg in ARTWORK_STATUS_CONFIG.items():
            if cfg.get('db_status') == status:
                return key
        return None

    @staticmethod
    def get_stage_config(stage_key):
        return ARTWORK_STATUS_CONFIG.get(stage_key, {})

    @staticmethod
    def log_action(artwork, user, action, stage='', comments='', status_before='', status_after='', ip=None):
        ArtworkApprovalLog.objects.create(
            artwork_request=artwork,
            user=user,
            action=action,
            stage=stage,
            comments=comments,
            status_before=status_before,
            status_after=status_after,
            ip_address=ip,
        )

    @classmethod
    def submit_for_approval(cls, artwork, user, ip=None):
        status_before = artwork.status
        next_cfg = ARTWORK_STATUS_CONFIG['marketing']
        artwork.status = next_cfg['db_status']
        artwork.is_rejected = False
        artwork.last_status_changed_by = user
        artwork.last_status_change = timezone.now()
        artwork.save()
        cls.log_action(
            artwork, user, 'submitted', 'marketing',
            status_before=status_before, status_after=artwork.status, ip=ip
        )
        ArtworkNotificationService.send_submission_notification(artwork, actor=user)
        return artwork

    @classmethod
    def approve(cls, artwork, stage_key, user, comments='', ip=None):
        cfg = ARTWORK_STATUS_CONFIG[stage_key]
        if stage_key == 'operations_hod':
            assert_user_can_approve_operations(user, artwork)
        if artwork.status != cfg.get('db_status'):
            raise PermissionDenied(
                'This artwork is not waiting at your approval stage right now. '
                'It may have already been actioned or moved on.'
            )
        prefix = cfg['field_prefix']
        status_before = artwork.status
        now = timezone.now()

        setattr(artwork, f'{prefix}_approved', True)
        setattr(artwork, f'{prefix}_rejected', False)
        setattr(artwork, f'{prefix}_comments', comments)
        setattr(artwork, f'{prefix}_date_approved', now)
        setattr(artwork, f'{prefix}_by', user)

        next_stage = cfg.get('next_stage')
        if next_stage == 'completed':
            artwork.status = ARTWORK_STATUS_CONFIG['completed']['db_status']
            artwork.current_user = None
        else:
            next_cfg = ARTWORK_STATUS_CONFIG[next_stage]
            artwork.status = next_cfg['db_status']

        artwork.is_rejected = False
        artwork.last_status_changed_by = user
        artwork.last_status_change = now
        artwork.save()

        cls.log_action(
            artwork, user, 'approved', stage_key, comments=comments,
            status_before=status_before, status_after=artwork.status, ip=ip
        )

        if next_stage == 'completed':
            ArtworkNotificationService.send_final_approval(artwork, stage_key)
        else:
            ArtworkNotificationService.send_approval_notification(
                artwork, stage_key, next_stage, actor=user,
            )
        return artwork

    @classmethod
    def reject(cls, artwork, stage_key, user, comments='', ip=None):
        cfg = ARTWORK_STATUS_CONFIG[stage_key]
        if stage_key == 'operations_hod':
            assert_user_can_approve_operations(user, artwork)
        if artwork.status != cfg.get('db_status'):
            raise PermissionDenied(
                'This artwork is not waiting at your approval stage right now. '
                'It may have already been actioned or moved on.'
            )
        prefix = cfg['field_prefix']
        status_before = artwork.status
        now = timezone.now()

        setattr(artwork, f'{prefix}_rejected', True)
        setattr(artwork, f'{prefix}_approved', False)
        setattr(artwork, f'{prefix}_comments', comments)
        setattr(artwork, f'{prefix}_date_rejected', now)
        setattr(artwork, f'{prefix}_by', user)

        artwork.is_rejected = True
        artwork.rejected_by = user
        artwork.rejection_stage = cfg['display']
        artwork.rejection_date = now
        artwork.rejection_comments = comments
        artwork.revision_count += 1
        artwork.status = ARTWORK_STATUS_CONFIG['design_revision']['db_status']
        artwork.current_user = artwork.created_by
        artwork.last_status_changed_by = user
        artwork.last_status_change = now
        artwork.save()

        cls.log_action(
            artwork, user, 'rejected', stage_key, comments=comments,
            status_before=status_before, status_after=artwork.status, ip=ip
        )
        ArtworkNotificationService.send_rejection_notification(artwork, stage_key, actor=user)
        return artwork

    @classmethod
    def reset_approval_flags(cls, artwork):
        """Reset all stage approval flags when resubmitting after revision."""
        for stage_key in STAGE_ORDER:
            prefix = ARTWORK_STATUS_CONFIG[stage_key]['field_prefix']
            setattr(artwork, f'{prefix}_approved', False)
            setattr(artwork, f'{prefix}_rejected', False)
            setattr(artwork, f'{prefix}_comments', '')
            setattr(artwork, f'{prefix}_date_approved', None)
            setattr(artwork, f'{prefix}_date_rejected', None)
            setattr(artwork, f'{prefix}_by', None)
        artwork.is_rejected = False
        artwork.rejected_by = None
        artwork.rejection_stage = ''
        artwork.rejection_date = None
        artwork.rejection_comments = ''


class ArtworkNotificationService:
    @staticmethod
    def _base_context(artwork, stage_key=None):
        ctx = {
            'artwork': artwork,
            'artwork_no': artwork.artwork_no,
            'product_name': artwork.product_name,
            'sku_size': artwork.sku_size,
            'reason_for_update': artwork.reason_for_update,
            'site_url': getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000'),
        }
        if stage_key:
            ctx['stage_name'] = ARTWORK_STATUS_CONFIG[stage_key]['display']
        return ctx

    @staticmethod
    def _get_group_emails(group_name):
        try:
            group = Group.objects.get(name=group_name)
            emails = []
            for user in group.user_set.filter(is_active=True):
                email = get_user_email(user)
                if email:
                    emails.append(email)
            return emails
        except Group.DoesNotExist:
            return []

    @classmethod
    def _get_stage_recipient_emails(cls, artwork, stage_key):
        """
        Primary recipients for a pending stage.

        Operations HOD uses category HOD/deputy mapping when configured;
        otherwise falls back to the whole OPERATIONS_HOD group.
        """
        cfg = ARTWORK_STATUS_CONFIG.get(stage_key) or {}
        group_name = cfg.get('group')
        if stage_key == 'operations_hod':
            if category_has_operations_mapping(artwork):
                emails = []
                for user in get_operations_assignees(artwork):
                    email = get_user_email(user)
                    if email:
                        emails.append(email)
                if not emails:
                    logger.warning(
                        'Mapped Operations assignees for %s have no usable email; '
                        'not broadcasting to the full OPERATIONS_HOD group',
                        artwork.artwork_no,
                    )
                return cls._unique_emails(emails)
            # Unmapped category — legacy group broadcast
        if group_name:
            return cls._get_group_emails(group_name)
        return []

    @staticmethod
    def _send_email(subject, template, context, to_emails, cc_emails=None):
        if not to_emails:
            logger.warning('No recipients for email: %s', subject)
            return
        html_content = render_to_string(template, context)
        text_content = f'{subject}\n\nView: {context.get("approval_url", "")}'
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to_emails,
            cc=cc_emails or [],
        )
        msg.attach_alternative(html_content, 'text/html')
        try:
            msg.send(fail_silently=False)
        except Exception as exc:
            logger.error('Failed to send email %s: %s', subject, exc)

    @classmethod
    def _approval_url(cls, artwork, url_name):
        if not url_name:
            return ''
        path = reverse(url_name, kwargs={'artwork_no': artwork.artwork_no})
        return f'{getattr(settings, "SITE_URL", "http://127.0.0.1:8000")}{path}'

    @classmethod
    def _actor_email(cls, user):
        if not user:
            return None
        return get_user_email(user)

    @classmethod
    def _to_with_actor(cls, primary_emails, actor_user):
        """Ensure both the next recipient(s) and the person who acted receive the alert."""
        to_emails = cls._unique_emails(list(primary_emails or []))
        actor_email = cls._actor_email(actor_user)
        if actor_email and actor_email not in to_emails:
            to_emails.append(actor_email)
        return to_emails

    @classmethod
    def send_submission_notification(cls, artwork, actor=None):
        cfg = ARTWORK_STATUS_CONFIG['marketing']
        ctx = cls._base_context(artwork, 'marketing')
        ctx['approval_url'] = cls._approval_url(artwork, 'marketing-approval')
        to_emails = cls._to_with_actor(cls._get_stage_recipient_emails(artwork, 'marketing'), actor)
        cc = cls._get_group_emails('ADMIN')
        subject = f'Artwork {artwork.artwork_no} - New Artwork Submission Pending Your Review'
        cls._send_email(subject, 'artwork_emails/submission.html', ctx, to_emails, cc)

    @classmethod
    def send_approval_notification(cls, artwork, approved_stage, next_stage, actor=None):
        next_cfg = ARTWORK_STATUS_CONFIG[next_stage]
        ctx = cls._base_context(artwork, approved_stage)
        ctx['next_stage_name'] = next_cfg['display']
        ctx['approval_url'] = cls._approval_url(artwork, next_cfg.get('approval_url_name'))
        to_emails = cls._to_with_actor(
            cls._get_stage_recipient_emails(artwork, next_stage), actor,
        )
        cc = []
        designer_email = get_user_email(artwork.created_by) if artwork.created_by else None
        if designer_email and designer_email not in to_emails:
            cc.append(designer_email)
        for stage in STAGE_ORDER:
            if stage == next_stage:
                break
            prefix = ARTWORK_STATUS_CONFIG[stage]['field_prefix']
            approver = getattr(artwork, f'{prefix}_by', None)
            if approver:
                email = get_user_email(approver)
                if email and email not in to_emails and email not in cc:
                    cc.append(email)
        cc = cls._unique_emails(cc + cls._get_group_emails('ADMIN'))
        subject = (
            f'Artwork {artwork.artwork_no} - Approved by {ctx["stage_name"]}, '
            f'Pending {next_cfg["display"]} Review'
        )
        template = next_cfg.get('approval_template', 'artwork_emails/marketing_approval.html')
        cls._send_email(subject, template, ctx, to_emails, cc)

    @staticmethod
    def _unique_emails(email_list):
        seen = set()
        result = []
        for email in email_list:
            if email and email not in seen:
                seen.add(email)
                result.append(email)
        return result

    @classmethod
    def _get_prior_stage_recipients(cls, artwork, stage_key):
        """All approvers and group members from stages before the rejection stage."""
        emails = []
        for stage in STAGE_ORDER:
            if stage == stage_key:
                break
            cfg = ARTWORK_STATUS_CONFIG[stage]
            emails.extend(cls._get_group_emails(cfg.get('group')))
            prefix = cfg['field_prefix']
            approver = getattr(artwork, f'{prefix}_by', None)
            if approver:
                email = get_user_email(approver)
                if email:
                    emails.append(email)
        return cls._unique_emails(emails)

    @classmethod
    def send_rejection_notification(cls, artwork, stage_key, actor=None):
        cfg = ARTWORK_STATUS_CONFIG[stage_key]
        ctx = cls._base_context(artwork, stage_key)
        ctx['rejection_comments'] = artwork.rejection_comments
        ctx['revision_count'] = artwork.revision_count
        ctx['approval_url'] = cls._approval_url(artwork, 'artwork-edit')
        designer_email = get_user_email(artwork.created_by) if artwork.created_by else None
        primary = [designer_email] if designer_email else []
        to_emails = cls._to_with_actor(primary, actor)
        cc = cls._get_prior_stage_recipients(artwork, stage_key)
        cc += cls._get_group_emails('ADMIN')
        cc = [e for e in cc if e not in to_emails]
        cc = cls._unique_emails(cc)
        subject = f'Artwork {artwork.artwork_no} - REJECTED by {cfg["display"]} — Revision Required'
        cls._send_email(subject, cfg['rejection_template'], ctx, to_emails, cc)

    @classmethod
    def send_final_approval(cls, artwork, stage_key):
        ctx = cls._base_context(artwork, stage_key)
        ctx['approval_url'] = cls._approval_url(artwork, 'procurement')
        to_emails = [get_user_email(artwork.created_by)] if artwork.created_by else []
        to_emails += cls._get_group_emails('PROCUREMENT')
        cc = cls._get_group_emails('ADMIN')
        for stage in STAGE_ORDER:
            prefix = ARTWORK_STATUS_CONFIG[stage]['field_prefix']
            if getattr(artwork, f'{prefix}_approved', False):
                approver = getattr(artwork, f'{prefix}_by', None)
                if approver:
                    email = get_user_email(approver)
                    if email:
                        cc.append(email)
        subject = f'Artwork {artwork.artwork_no} - FULLY APPROVED — Procurement to fill SAP details'
        cls._send_email(subject, 'artwork_emails/final_approved.html', ctx, to_emails, cc)

    @classmethod
    def send_deadline_reminder(cls, artwork, stage_key):
        cfg = ARTWORK_STATUS_CONFIG[stage_key]
        ctx = cls._base_context(artwork, stage_key)
        ctx['approval_url'] = cls._approval_url(artwork, cfg.get('approval_url_name'))
        ctx['timeline_hours'] = cfg.get('timeline_hours', 24)
        to_emails = cls._get_stage_recipient_emails(artwork, stage_key)
        cc = []
        designer_email = get_user_email(artwork.created_by) if artwork.created_by else None
        if designer_email and designer_email not in to_emails:
            cc.append(designer_email)
        subject = f'Artwork {artwork.artwork_no} - Reminder: Pending {cfg["display"]} Approval'
        cls._send_email(subject, 'artwork_emails/deadline_reminder.html', ctx, to_emails, cc)
