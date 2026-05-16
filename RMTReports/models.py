from django.contrib import admin
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
import logging
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import User
from rest_framework import serializers
from django.core.validators import MinValueValidator, MaxValueValidator
import json

# Set up logging
logger = logging.getLogger(__name__)

class TemporaryReportSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    rmtr_no = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return f"Session for {self.user.username}"

class Supplier(models.Model):
    name = models.CharField(max_length=255)
    supplier_email = models.EmailField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['name', 'supplier_email']

class SupplierCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['name', 'supplier_email']

class Plant(models.Model):
    name = models.CharField(max_length=100)
    hod = models.CharField(max_length=100)
    hod_email = models.EmailField(max_length=254, blank=True, default='')
    deputy_hod_email = models.EmailField(max_length=254, blank=True, default='')

    def __str__(self):
        return self.name

    def get_notification_emails(self):
        emails = ['ict@kapa-oil.com']
        if self.hod_email:
            emails.append(self.hod_email)
        if self.deputy_hod_email:
            emails.append(self.deputy_hod_email)
        return list(set(emails))

class ApprovedManagement(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class MaterialType(models.Model):
    name = models.CharField(max_length=50, default='Unknown')

class RMTRRequest(models.Model):
    rmtr_no = models.CharField(max_length=100, blank=True, unique=True)
    supplier = models.ForeignKey('Supplier', on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    material_name = models.CharField(max_length=500, blank=True)
    material_type = models.CharField(max_length=100, blank=True)
    sub_category = models.CharField(max_length=100, blank=True)
    tests = models.CharField(max_length=1000, blank=True)
    plant = models.ForeignKey('Plant', on_delete=models.CASCADE)
    approved_mgt = models.CharField(max_length=100, blank=True, null=True)
    second_approver = models.CharField(max_length=100, blank=True, null=True)
    requested_by = models.CharField(max_length=500, null=True, blank=True)
    justification = models.TextField()
    uom = models.CharField(max_length=20, default='N/A')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    specs = models.CharField(max_length=800, null=True, blank=True)
    image = models.ImageField(upload_to='rmtr/images/', null=True, blank=True, default='images/default.jpg')
    status = models.CharField(max_length=100, default='Pending: HOD Purchase Approval')
    date_created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='rmtr_created_rmtrs')
    current_user = models.ForeignKey(User, related_name='rmtr_current_users', on_delete=models.PROTECT)
    last_status_change = models.DateTimeField(null=True, help_text="Timestamp of the last status change")
    last_status_changed_by = models.ForeignKey(User, related_name='rmtr_status_changes', on_delete=models.SET_NULL, null=True, blank=True)
    last_reminder_sent = models.DateTimeField(null=True, help_text="Timestamp of the last reminder email sent")
    lab_timeline_days = models.IntegerField(
        null=True, blank=True, help_text="Number of business days allowed for lab testing",
        validators=[MinValueValidator(1, message="Timeline must be at least 1 day"), MaxValueValidator(10, message="Timeline cannot exceed 10 days")]
    )
    lab_deadline = models.DateTimeField(null=True, blank=True, help_text="Actual deadline for lab testing (excluding Sundays)")
    hod_purchase_priority = models.CharField(max_length=100, blank=True)
    hod_purchase_sensitivity = models.CharField(max_length=100, blank=True)
    hod_purchase_approved = models.BooleanField(default=False)
    hod_purchase_rejected = models.BooleanField(default=False)
    hod_purchase_comments = models.TextField(blank=True)
    hod_purchase_date_approved = models.DateTimeField(null=True, blank=True)
    hod_purchase_date_rejected = models.DateTimeField(null=True, blank=True)
    hod_purchase_by = models.ForeignKey(User, related_name='rmtr_hod_purchase_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    management_approved = models.BooleanField(default=False)
    management_rejected = models.BooleanField(default=False)
    management_comments = models.TextField(blank=True)
    management_date_approved = models.DateTimeField(null=True, blank=True)
    management_date_rejected = models.DateTimeField(null=True, blank=True)
    management_by = models.ForeignKey(User, related_name='rmtr_management_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    management_approved_2 = models.BooleanField(default=False)
    management_rejected_2 = models.BooleanField(default=False)
    management_comments_2 = models.TextField(blank=True)
    management_date_approved_2 = models.DateTimeField(null=True, blank=True)
    management_date_rejected_2 = models.DateTimeField(null=True, blank=True)
    management_by_2 = models.ForeignKey(User, related_name='rmtr_management_approvals_2', on_delete=models.SET_NULL, null=True, blank=True)
    fm_approved = models.BooleanField(default=False)
    fm_rejected = models.BooleanField(default=False)
    fm_comments = models.TextField(blank=True)
    fm_date_approved = models.DateTimeField(null=True, blank=True)
    fm_date_rejected = models.DateTimeField(null=True, blank=True)
    fm_by = models.ForeignKey(User, related_name='rmtr_fm_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    hod_approved = models.BooleanField(default=False)
    hod_rejected = models.BooleanField(default=False)
    hod_comments = models.TextField(blank=True)
    hod_date_approved = models.DateTimeField(null=True, blank=True)
    hod_date_rejected = models.DateTimeField(null=True, blank=True)
    hod_by = models.ForeignKey(User, related_name='rmtr_hod_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    labtimeline = models.CharField(null=True, blank=True)
    stage_deadline = models.DateTimeField(null=True, blank=True)
    tests_carried_out1 = models.CharField(max_length=300, blank=True)
    sample_results1 = models.CharField(max_length=300, blank=True)
    raw_material_results1 = models.CharField(max_length=300, blank=True)
    kapa_standards1 = models.CharField(max_length=300, blank=True)
    tests_carried_out2 = models.CharField(max_length=300, blank=True)
    sample_results2 = models.CharField(max_length=300, blank=True)
    raw_material_results2 = models.CharField(max_length=300, blank=True)
    kapa_standards2 = models.CharField(max_length=300, blank=True)
    tests_carried_out3 = models.CharField(max_length=300, blank=True)
    sample_results3 = models.CharField(max_length=300, blank=True)
    raw_material_results3 = models.CharField(max_length=300, blank=True)
    kapa_standards3 = models.CharField(max_length=300, blank=True)
    tests_carried_out4 = models.CharField(max_length=300, blank=True)
    sample_results4 = models.CharField(max_length=300, blank=True)
    raw_material_results4 = models.CharField(max_length=300, blank=True)
    kapa_standards4 = models.CharField(max_length=300, blank=True)
    tests_carried_out5 = models.CharField(max_length=300, blank=True)
    sample_results5 = models.CharField(max_length=300, blank=True)
    raw_material_results5 = models.CharField(max_length=300, blank=True)
    kapa_standards5 = models.CharField(max_length=300, blank=True)
    tests_carried_out6 = models.CharField(max_length=300, blank=True)
    sample_results6 = models.CharField(max_length=300, blank=True)
    raw_material_results6 = models.CharField(max_length=300, blank=True)
    kapa_standards6 = models.CharField(max_length=300, blank=True)
    tests_carried_out7 = models.CharField(max_length=300, blank=True)
    sample_results7 = models.CharField(max_length=300, blank=True)
    raw_material_results7 = models.CharField(max_length=300, blank=True)
    kapa_standards7 = models.CharField(max_length=300, blank=True)
    tests_carried_out8 = models.CharField(max_length=300, blank=True)
    sample_results8 = models.CharField(max_length=300, blank=True)
    raw_material_results8 = models.CharField(max_length=300, blank=True)
    kapa_standards8 = models.CharField(max_length=300, blank=True)
    tests_carried_out9 = models.CharField(max_length=300, blank=True)
    sample_results9 = models.CharField(max_length=300, blank=True)
    raw_material_results9 = models.CharField(max_length=300, blank=True)
    kapa_standards9 = models.CharField(max_length=300, blank=True)
    tests_carried_out10 = models.CharField(max_length=300, blank=True)
    sample_results10 = models.CharField(max_length=300, blank=True)
    raw_material_results10 = models.CharField(max_length=300, blank=True)
    kapa_standards10 = models.CharField(max_length=300, blank=True)
    tests_carried_out11 = models.CharField(max_length=300, blank=True)
    sample_results11 = models.CharField(max_length=300, blank=True)
    raw_material_results11 = models.CharField(max_length=300, blank=True)
    kapa_standards11 = models.CharField(max_length=300, blank=True)
    tests_carried_out12 = models.CharField(max_length=300, blank=True)
    sample_results12 = models.CharField(max_length=300, blank=True)
    raw_material_results12 = models.CharField(max_length=300, blank=True)
    kapa_standards12 = models.CharField(max_length=300, blank=True)
    tests_carried_out13 = models.CharField(max_length=300, blank=True)
    sample_results13 = models.CharField(max_length=300, blank=True)
    raw_material_results13 = models.CharField(max_length=300, blank=True)
    kapa_standards13 = models.CharField(max_length=300, blank=True)
    tests_carried_out14 = models.CharField(max_length=300, blank=True)
    sample_results14 = models.CharField(max_length=300, blank=True)
    raw_material_results14 = models.CharField(max_length=300, blank=True)
    kapa_standards14 = models.CharField(max_length=300, blank=True)
    tests_carried_out15 = models.CharField(max_length=300, blank=True)
    sample_results15 = models.CharField(max_length=300, blank=True)
    raw_material_results15 = models.CharField(max_length=300, blank=True)
    kapa_standards15 = models.CharField(max_length=300, blank=True)
    tests_carried_out16 = models.CharField(max_length=300, blank=True)
    sample_results16 = models.CharField(max_length=300, blank=True)
    raw_material_results16 = models.CharField(max_length=300, blank=True)
    kapa_standards16 = models.CharField(max_length=300, blank=True)
    test_image = models.ImageField(upload_to='rmtr/test_images/', null=True, blank=True, default='test_images/default.jpg')
    lab_qc_comments = models.TextField(blank=True)
    tests_done_by = models.CharField(max_length=255, null=True, blank=True)
    test_results_modified_by = models.ForeignKey(User, related_name='rmtr_test_results_modifications', on_delete=models.SET_NULL, null=True, blank=True)
    test_results_modified_at = models.DateTimeField(null=True, blank=True)
    retest_requested_by = models.ForeignKey(User, related_name='rmtr_retest_requests', on_delete=models.SET_NULL, null=True, blank=True)
    retest_requested_date = models.DateTimeField(null=True, blank=True)
    retest_reason = models.TextField(blank=True)
    retest_stage = models.CharField(max_length=50, blank=True)
    retest_date = models.DateTimeField(null=True, blank=True)
    retest_history = models.JSONField(default=list, blank=True)
    previous_status = models.CharField(max_length=50, blank=True)
    qao_approved = models.BooleanField(default=False)
    qao_rejected = models.BooleanField(default=False)
    qao_comments = models.TextField(blank=True)
    qao_date_approved = models.DateTimeField(null=True, blank=True)
    qao_date_rejected = models.DateTimeField(null=True, blank=True)
    qao_by = models.ForeignKey(User, related_name='rmtr_qao_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    hod_test_approved = models.BooleanField(default=False)
    hod_test_rejected = models.BooleanField(default=False)
    hod_test_comments = models.TextField(null=True, blank=True)
    hod_test_date_approved = models.DateTimeField(null=True, blank=True)
    hod_test_date_rejected = models.DateTimeField(null=True, blank=True)
    hod_test_by = models.ForeignKey(User, related_name='rmtr_hod_test_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    fm_test_approved = models.BooleanField(default=False)
    fm_test_rejected = models.BooleanField(default=False)
    fm_test_comments = models.TextField(blank=True)
    fm_test_date_approved = models.DateTimeField(null=True, blank=True)
    fm_test_date_rejected = models.DateTimeField(null=True, blank=True)
    fm_test_by = models.ForeignKey(User, related_name='rmtr_fm_test_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    management_test_approved = models.BooleanField(default=False)
    management_test_rejected = models.BooleanField(default=False)
    management_test_comments = models.TextField(blank=True)
    management_test_date_approved = models.DateTimeField(null=True, blank=True)
    management_test_date_rejected = models.DateTimeField(null=True, blank=True)
    management_test_by = models.ForeignKey(User, related_name='rmtr_management_test_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    milan_approved = models.BooleanField(default=False)
    milan_rejected = models.BooleanField(default=False)
    milan_comments = models.TextField(blank=True)
    milan_date_approved = models.DateTimeField(null=True, blank=True)
    milan_date_rejected = models.DateTimeField(null=True, blank=True)
    milan_by = models.ForeignKey(User, related_name='rmtr_milan_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Local Purchase RMTR"

    def generate_next_rmtr_no(self):
        current_year = timezone.now().year
        prefix = f"{current_year}-"
        last_instance = RMTRRequest.objects.filter(date__year=current_year).order_by('-id').first()
        if last_instance:
            try:
                last_number = int(last_instance.rmtr_no.split('-')[1])
            except (IndexError, ValueError):
                last_number = 0
            next_number = last_number + 1
        else:
            next_number = 1
        return f"{prefix}{next_number:04d}"

    def save(self, *args, **kwargs):
        if not self.rmtr_no:
            self.rmtr_no = self.generate_next_rmtr_no()
        if self.rmtr_no and self.image:
            self.image.name = f"rmtr_{self.rmtr_no}/{self.image.name.split('/')[-1]}"
        if self.rmtr_no and self.test_image:
            self.test_image.name = f"rmtr_{self.rmtr_no}/test_images/{self.test_image.name.split('/')[-1]}"
        with transaction.atomic():
            super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if self.hod_purchase_approved and not self.hod_purchase_by:
            errors['hod_purchase_by'] = "HOD Purchase approver must be set if approved."
        if self.management_approved and not self.management_by:
            errors['management_by'] = "Management approver must be set if approved."
        if self.management_approved_2 and not self.management_by_2:
            errors['management_by_2'] = "Second Management approver must be set if approved."
        if self.fm_approved and not self.fm_by:
            errors['fm_by'] = "FM approver must be set if approved."
        if self.hod_approved and not self.hod_by:
            errors['hod_by'] = "HOD approver must be set if approved."
        if self.qao_approved and not self.qao_by:
            errors['qao_by'] = "QAO approver must be set if approved."
        if self.hod_test_approved and not self.hod_test_by:
            errors['hod_test_by'] = "HOD Test approver must be set if approved."
        if self.fm_test_approved and not self.fm_test_by:
            errors['fm_test_by'] = "FM Test approver must be set if approved."
        if self.management_test_approved and not self.management_test_by:
            errors['management_test_by'] = "Management Test approver must be set if approved."
        if self.milan_approved and not self.milan_by:
            errors['milan_by'] = "Milan approver must be set if approved."
        if errors:
            raise ValidationError(errors)

    def get_audit_history(self):
        history = []
        for log in self.approval_logs.all():
            history.append({
                'action': log.action,
                'user': log.user.username if log.user else 'Unknown',
                'timestamp': log.created_at,
                'comments': log.comments,
                'status_before': log.status_before,
                'status_after': log.status_after,
                'field_changes': log.field_changes,
                'ip_address': log.ip_address,
                'user_agent': log.user_agent
            })
        for retest in self.rmtr_retests.all():
            history.append({
                'action': 'retest_requested',
                'user': retest.requested_by.username if retest.requested_by else 'Unknown',
                'timestamp': retest.requested_at,
                'comments': retest.comments,
                'retest_reason': retest.reason,
                'status_before': retest.original_status,
                'status_after': 'Retest Requested'
            })
        return sorted(history, key=lambda x: x['timestamp'], reverse=True)

    def title_case_approved_mgt(self):
        return self.approved_mgt.title() if self.approved_mgt else self.approved_mgt

    def __str__(self):
        return f"RMTR-{self.rmtr_no} by {self.supplier.name}, {self.supplier.id}"

class ApprovalLog(models.Model):
    ACTIONS = [
        ('created', 'Created'),
        ('status_changed', 'Status Changed'),
        ('test_results_updated', 'Test Results Updated'),
        ('retest_requested', 'Retest Requested'),
        ('retest_completed', 'Retest Completed'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('edited', 'Report Edited')
    ]
    report = models.ForeignKey(RMTRRequest, on_delete=models.CASCADE, related_name='approval_logs', null=True, blank=True)
    imp_report = models.ForeignKey('IMP_RMTRRequest', on_delete=models.CASCADE, related_name='imp_approval_logs', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTIONS)
    comments = models.TextField(blank=True)
    retest_reason = models.TextField(blank=True, null=True)
    status_before = models.CharField(max_length=100, blank=True)
    status_after = models.CharField(max_length=100, blank=True)
    field_changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        report_id = self.report.rmtr_no if self.report else self.imp_report.imp_rmtr_no if self.imp_report else 'Unknown'
        return f"{report_id} - {self.action} by {self.user.username if self.user else 'Unknown'}"

class RetestRequest(models.Model):
    rmtr_no = models.ForeignKey('RMTRRequest', on_delete=models.CASCADE, related_name='rmtr_retests', null=True, blank=True)
    imp_rmtr_no = models.ForeignKey('IMP_RMTRRequest', on_delete=models.CASCADE, related_name='imp_rmtr_retests', null=True, blank=True)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()
    comments = models.TextField(blank=True)
    completed = models.BooleanField(default=False)
    test_data = models.JSONField(default=dict)
    original_status = models.CharField(max_length=100)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        report_id = self.rmtr_no.rmtr_no if self.rmtr_no else self.imp_rmtr_no.imp_rmtr_no if self.imp_rmtr_no else 'Unknown'
        return f"Retest for {report_id} by {self.requested_by.username if self.requested_by else 'Unknown'}"

class IMP_RMTRRequest(models.Model):
    imp_rmtr_no = models.CharField(max_length=20, unique=True)
    supplier = models.ForeignKey('Supplier', on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)
    material_name = models.CharField(max_length=800, blank=True)
    material_type = models.CharField(max_length=200, blank=True)
    sub_category = models.CharField(max_length=200, blank=True)
    tests = models.CharField(max_length=1000, blank=True)
    plant = models.ForeignKey('Plant', on_delete=models.CASCADE)
    approved_mgt = models.CharField(max_length=200, blank=True, null=True)
    second_approver = models.CharField(max_length=200, blank=True, null=True)
    status = models.CharField(max_length=200, default='Pending: HOD Purchase Approval')
    requested_by = models.CharField(max_length=200, null=True, blank=True)
    justification = models.TextField()
    uom = models.CharField(max_length=200, default='N/A')
    quantity = models.IntegerField(null=True, blank=True)
    specs = models.CharField(max_length=700, null=True, blank=True)
    image = models.ImageField(upload_to='imp/images/', null=True, blank=True, default='images/default.jpg')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='imp_created_rmtrs')
    current_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='imp_current_rmtrs')
    last_status_change = models.DateTimeField(null=True, help_text="Timestamp of the last status change")
    last_status_changed_by = models.ForeignKey(User, related_name='imp_status_changes', on_delete=models.SET_NULL, null=True, blank=True)
    last_reminder_sent = models.DateTimeField(null=True, help_text="Timestamp of the last reminder email sent")
    lab_timeline_days = models.IntegerField(
        null=True, blank=True, help_text="Number of business days allowed for lab testing",
        validators=[MinValueValidator(1, message="Timeline must be at least 1 day"), MaxValueValidator(10, message="Timeline cannot exceed 10 days")]
    )
    lab_deadline = models.DateTimeField(null=True, blank=True, help_text="Actual deadline for lab testing (excluding Sundays)")
    hod_purchase_priority = models.CharField(max_length=100, blank=True)
    hod_purchase_sensitivity = models.CharField(max_length=100, blank=True)
    hod_purchase_approved = models.BooleanField(default=False)
    hod_purchase_rejected = models.BooleanField(default=False)
    hod_purchase_comments = models.TextField(blank=True)
    hod_purchase_date_approved = models.DateTimeField(null=True, blank=True)
    hod_purchase_date_rejected = models.DateTimeField(null=True, blank=True)
    hod_purchase_by = models.ForeignKey(User, related_name='imp_hod_purchase_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    management_approved = models.BooleanField(default=False)
    management_rejected = models.BooleanField(default=False)
    management_comments = models.TextField(blank=True)
    management_date_approved = models.DateTimeField(null=True, blank=True)
    management_date_rejected = models.DateTimeField(null=True, blank=True)
    management_by = models.ForeignKey(User, related_name='imp_management_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    management_approved_2 = models.BooleanField(default=False)
    management_rejected_2 = models.BooleanField(default=False)
    management_comments_2 = models.TextField(blank=True)
    management_date_approved_2 = models.DateTimeField(null=True, blank=True)
    management_date_rejected_2 = models.DateTimeField(null=True, blank=True)
    management_by_2 = models.ForeignKey(User, related_name='imp_management_approvals_2', on_delete=models.SET_NULL, null=True, blank=True)
    fm_approved = models.BooleanField(default=False)
    fm_rejected = models.BooleanField(default=False)
    fm_comments = models.TextField(blank=True)
    fm_date_approved = models.DateTimeField(null=True, blank=True)
    fm_date_rejected = models.DateTimeField(null=True, blank=True)
    fm_by = models.ForeignKey(User, related_name='imp_fm_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    hod_approved = models.BooleanField(default=False)
    hod_rejected = models.BooleanField(default=False)
    hod_comments = models.TextField(blank=True)
    hod_date_approved = models.DateTimeField(null=True, blank=True)
    hod_date_rejected = models.DateTimeField(null=True, blank=True)
    hod_by = models.ForeignKey(User, related_name='imp_hod_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    labtimeline = models.CharField(null=True, blank=True)
    stage_deadline = models.DateTimeField(null=True, blank=True)
    tests_carried_out1 = models.CharField(max_length=300, blank=True)
    sample_results1 = models.CharField(max_length=300, blank=True)
    raw_material_results1 = models.CharField(max_length=300, blank=True)
    kapa_standards1 = models.CharField(max_length=300, blank=True)
    tests_carried_out2 = models.CharField(max_length=300, blank=True)
    sample_results2 = models.CharField(max_length=300, blank=True)
    raw_material_results2 = models.CharField(max_length=300, blank=True)
    kapa_standards2 = models.CharField(max_length=300, blank=True)
    tests_carried_out3 = models.CharField(max_length=300, blank=True)
    sample_results3 = models.CharField(max_length=300, blank=True)
    raw_material_results3 = models.CharField(max_length=300, blank=True)
    kapa_standards3 = models.CharField(max_length=300, blank=True)
    tests_carried_out4 = models.CharField(max_length=300, blank=True)
    sample_results4 = models.CharField(max_length=300, blank=True)
    raw_material_results4 = models.CharField(max_length=300, blank=True)
    kapa_standards4 = models.CharField(max_length=300, blank=True)
    tests_carried_out5 = models.CharField(max_length=300, blank=True)
    sample_results5 = models.CharField(max_length=300, blank=True)
    raw_material_results5 = models.CharField(max_length=300, blank=True)
    kapa_standards5 = models.CharField(max_length=300, blank=True)
    tests_carried_out6 = models.CharField(max_length=300, blank=True)
    sample_results6 = models.CharField(max_length=300, blank=True)
    raw_material_results6 = models.CharField(max_length=300, blank=True)
    kapa_standards6 = models.CharField(max_length=300, blank=True)
    tests_carried_out7 = models.CharField(max_length=300, blank=True)
    sample_results7 = models.CharField(max_length=300, blank=True)
    raw_material_results7 = models.CharField(max_length=300, blank=True)
    kapa_standards7 = models.CharField(max_length=300, blank=True)
    tests_carried_out8 = models.CharField(max_length=300, blank=True)
    sample_results8 = models.CharField(max_length=300, blank=True)
    raw_material_results8 = models.CharField(max_length=300, blank=True)
    kapa_standards8 = models.CharField(max_length=300, blank=True)
    tests_carried_out9 = models.CharField(max_length=300, blank=True)
    sample_results9 = models.CharField(max_length=300, blank=True)
    raw_material_results9 = models.CharField(max_length=300, blank=True)
    kapa_standards9 = models.CharField(max_length=300, blank=True)
    tests_carried_out10 = models.CharField(max_length=300, blank=True)
    sample_results10 = models.CharField(max_length=300, blank=True)
    raw_material_results10 = models.CharField(max_length=300, blank=True)
    kapa_standards10 = models.CharField(max_length=300, blank=True)
    tests_carried_out11 = models.CharField(max_length=300, blank=True)
    sample_results11 = models.CharField(max_length=300, blank=True)
    raw_material_results11 = models.CharField(max_length=300, blank=True)
    kapa_standards11 = models.CharField(max_length=300, blank=True)
    tests_carried_out12 = models.CharField(max_length=300, blank=True)
    sample_results12 = models.CharField(max_length=300, blank=True)
    raw_material_results12 = models.CharField(max_length=300, blank=True)
    kapa_standards12 = models.CharField(max_length=300, blank=True)
    tests_carried_out13 = models.CharField(max_length=300, blank=True)
    sample_results13 = models.CharField(max_length=300, blank=True)
    raw_material_results13 = models.CharField(max_length=300, blank=True)
    kapa_standards13 = models.CharField(max_length=300, blank=True)
    tests_carried_out14 = models.CharField(max_length=300, blank=True)
    sample_results14 = models.CharField(max_length=300, blank=True)
    raw_material_results14 = models.CharField(max_length=300, blank=True)
    kapa_standards14 = models.CharField(max_length=300, blank=True)
    tests_carried_out15 = models.CharField(max_length=300, blank=True)
    sample_results15 = models.CharField(max_length=300, blank=True)
    raw_material_results15 = models.CharField(max_length=300, blank=True)
    kapa_standards15 = models.CharField(max_length=300, blank=True)
    tests_carried_out16 = models.CharField(max_length=300, blank=True)
    sample_results16 = models.CharField(max_length=300, blank=True)
    raw_material_results16 = models.CharField(max_length=300, blank=True)
    kapa_standards16 = models.CharField(max_length=300, blank=True)
    test_image = models.ImageField(upload_to='imp/test_images/', null=True, blank=True, default='test_images/default.jpg')
    lab_qc_comments = models.TextField(blank=True)
    tests_done_by = models.CharField(max_length=255, null=True, blank=True)
    test_results_modified_by = models.ForeignKey(User, related_name='imp_test_results_modifications', on_delete=models.SET_NULL, null=True, blank=True)
    test_results_modified_at = models.DateTimeField(null=True, blank=True)
    retest_requested_by = models.ForeignKey(User, related_name='imp_retest_requests', on_delete=models.SET_NULL, null=True, blank=True)
    retest_requested_date = models.DateTimeField(null=True, blank=True)
    retest_reason = models.TextField(blank=True)
    retest_stage = models.CharField(max_length=50, blank=True)
    retest_date = models.DateTimeField(null=True, blank=True)
    retest_history = models.JSONField(default=list, blank=True)
    previous_status = models.CharField(max_length=50, blank=True)
    qao_approved = models.BooleanField(default=False)
    qao_rejected = models.BooleanField(default=False)
    qao_comments = models.TextField(blank=True)
    qao_date_approved = models.DateTimeField(null=True, blank=True)
    qao_date_rejected = models.DateTimeField(null=True, blank=True)
    qao_by = models.ForeignKey(User, related_name='imp_qao_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    hod_test_approved = models.BooleanField(default=False)
    hod_test_rejected = models.BooleanField(default=False)
    hod_test_comments = models.TextField(null=True, blank=True)
    hod_test_date_approved = models.DateTimeField(null=True, blank=True)
    hod_test_date_rejected = models.DateTimeField(null=True, blank=True)
    hod_test_by = models.ForeignKey(User, related_name='imp_hod_test_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    fm_test_approved = models.BooleanField(default=False)
    fm_test_rejected = models.BooleanField(default=False)
    fm_test_comments = models.TextField(blank=True)
    fm_test_date_approved = models.DateTimeField(null=True, blank=True)
    fm_test_date_rejected = models.DateTimeField(null=True, blank=True)
    fm_test_by = models.ForeignKey(User, related_name='imp_fm_test_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    management_test_approved = models.BooleanField(default=False)
    management_test_rejected = models.BooleanField(default=False)
    management_test_comments = models.TextField(blank=True)
    management_test_date_approved = models.DateTimeField(null=True, blank=True)
    management_test_date_rejected = models.DateTimeField(null=True, blank=True)
    management_test_by = models.ForeignKey(User, related_name='imp_management_test_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    milan_approved = models.BooleanField(default=False)
    milan_rejected = models.BooleanField(default=False)
    milan_comments = models.TextField(blank=True)
    milan_date_approved = models.DateTimeField(null=True, blank=True)
    milan_date_rejected = models.DateTimeField(null=True, blank=True)
    milan_by = models.ForeignKey(User, related_name='imp_milan_approvals', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Imports RMTR"

    def generate_next_imp_rmtr_no(self):
        current_year = timezone.now().year
        prefix = f"IMP-{current_year}-"
        last_instance = IMP_RMTRRequest.objects.filter(date_created__year=current_year).order_by('-id').first()
        if last_instance:
            try:
                last_number = int(last_instance.imp_rmtr_no.split('-')[2])
            except (IndexError, ValueError):
                last_number = 0
            next_number = last_number + 1
        else:
            next_number = 1
        return f"{prefix}{next_number:04d}"

    def save(self, *args, **kwargs):
        if not self.imp_rmtr_no:
            self.imp_rmtr_no = self.generate_next_imp_rmtr_no()
        if self.imp_rmtr_no and self.image:
            self.image.name = f"imp_{self.imp_rmtr_no}/{self.image.name.split('/')[-1]}"
        if self.imp_rmtr_no and self.test_image:
            self.test_image.name = f"imp_{self.imp_rmtr_no}/test_images/{self.test_image.name.split('/')[-1]}"
        with transaction.atomic():
            super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if self.hod_purchase_approved and not self.hod_purchase_by:
            errors['hod_purchase_by'] = "HOD Purchase approver must be set if approved."
        if self.management_approved and not self.management_by:
            errors['management_by'] = "Management approver must be set if approved."
        if self.management_approved_2 and not self.management_by_2:
            errors['management_by_2'] = "Second Management approver must be set if approved."
        if self.fm_approved and not self.fm_by:
            errors['fm_by'] = "FM approver must be set if approved."
        if self.hod_approved and not self.hod_by:
            errors['hod_by'] = "HOD approver must be set if approved."
        if self.qao_approved and not self.qao_by:
            errors['qao_by'] = "QAO approver must be set if approved."
        if self.hod_test_approved and not self.hod_test_by:
            errors['hod_test_by'] = "HOD Test approver must be set if approved."
        if self.fm_test_approved and not self.fm_test_by:
            errors['fm_test_by'] = "FM Test approver must be set if approved."
        if self.management_test_approved and not self.management_test_by:
            errors['management_test_by'] = "Management Test approver must be set if approved."
        if self.milan_approved and not self.milan_by:
            errors['milan_by'] = "Milan approver must be set if approved."
        if errors:
            raise ValidationError(errors)

    def get_audit_history(self):
        history = []
        for log in self.imp_approval_logs.all():
            history.append({
                'action': log.action,
                'user': log.user.username if log.user else 'Unknown',
                'timestamp': log.created_at,
                'comments': log.comments,
                'status_before': log.status_before,
                'status_after': log.status_after,
                'field_changes': log.field_changes,
                'ip_address': log.ip_address,
                'user_agent': log.user_agent
            })
        for retest in self.imp_rmtr_retests.all():
            history.append({
                'action': 'retest_requested',
                'user': retest.requested_by.username if retest.requested_by else 'Unknown',
                'timestamp': retest.requested_at,
                'comments': retest.comments,
                'retest_reason': retest.reason,
                'status_before': retest.original_status,
                'status_after': 'Retest Requested'
            })
        return sorted(history, key=lambda x: x['timestamp'], reverse=True)

    def title_case_approved_mgt(self):
        return self.approved_mgt.title() if self.approved_mgt else self.approved_mgt

    def __str__(self):
        return f"{self.imp_rmtr_no} by {self.supplier.name}, {self.supplier.id}"

class DocumentAttachment(models.Model):
    report = models.ForeignKey('IMP_RMTRRequest', on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='')
    file_type = models.CharField(max_length=50)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.file and self.report.imp_rmtr_no:
            original_name = self.file.name.split('/')[-1]
            folder = 'images' if self.file_type == 'image' else 'pdfs'
            self.file.name = f'imp_rmtr/{self.report.imp_rmtr_no}/{folder}/{original_name}'
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.file_type} - {self.file.name} for {self.report.imp_rmtr_no}"

class Approval(models.Model):
    APPROVAL_TYPES = [
        ('HOD_PURCHASE', 'HOD Purchase'),
        ('MANAGEMENT', 'Management'),
        ('MANAGEMENT_2', 'Management_2'),
        ('HOD_TEST', 'HOD_TEST'),
        ('FM', 'FM'),
        ('HOD', 'HOD'),
        ('QAO', 'QAO'),
        ('MILAN', 'Milan')
    ]
    rmtr_request = models.ForeignKey('RMTRRequest', on_delete=models.CASCADE, null=True, blank=True)
    imp_rmtr_request = models.ForeignKey('IMP_RMTRRequest', on_delete=models.CASCADE, null=True, blank=True)
    approval_type = models.CharField(max_length=20, choices=APPROVAL_TYPES, default='pending')
    approved = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    comments = models.TextField(blank=True, null=True)
    date_approved = models.DateTimeField(null=True)
    date_rejected = models.DateTimeField(null=True)

class HODPurchaseApproval(models.Model):
    request = models.OneToOneField(RMTRRequest, on_delete=models.CASCADE, related_name='hod_purchase_approval')
    hod_purchase_priority = models.CharField(max_length=100, blank=True)
    hod_purchase_sensitivity = models.CharField(max_length=100, blank=True)
    hod_purchase_approved = models.BooleanField(default=False)
    hod_purchase_rejected = models.BooleanField(default=False)
    hod_purchase_comments = models.TextField(blank=True)
    hod_purchase_date_approved = models.DateTimeField(null=True, blank=True)
    hod_purchase_date_rejected = models.DateTimeField(null=True, blank=True)

class ManagementApproval(models.Model):
    request = models.OneToOneField(RMTRRequest, on_delete=models.CASCADE, related_name='management_approval')
    management_approved = models.BooleanField(default=False)
    management_rejected = models.BooleanField(default=False)
    management_comments = models.TextField(blank=True)
    management_date_approved = models.DateTimeField(null=True, blank=True)
    management_date_rejected = models.DateTimeField(null=True, blank=True)

class FMApproval(models.Model):
    request = models.OneToOneField(RMTRRequest, on_delete=models.CASCADE, related_name='fm_approval')
    hod_plant = models.CharField(max_length=100, null=True, blank=True)
    fm_approved = models.BooleanField(default=False)
    fm_rejected = models.BooleanField(default=False)
    fm_comments = models.TextField(blank=True)
    fm_date_approved = models.DateTimeField(null=True, blank=True)
    fm_date_rejected = models.DateTimeField(null=True, blank=True)

class HODApproval(models.Model):
    request = models.OneToOneField(RMTRRequest, on_delete=models.CASCADE, related_name='hod_approval')
    hod_approved = models.BooleanField(default=False)
    hod_rejected = models.BooleanField(default=False)
    hod_comments = models.TextField(blank=True)
    hod_date_approved = models.DateTimeField(null=True, blank=True)
    hod_date_rejected = models.DateTimeField(null=True, blank=True)

class TestResults(models.Model):
    rmtr_request = models.ForeignKey('RMTRRequest', on_delete=models.CASCADE, null=True, blank=True)
    test_number = models.IntegerField(null=True, blank=True)
    tests_carried_out = models.CharField(max_length=300, blank=True)
    sample_results = models.CharField(max_length=300, blank=True)
    raw_material_results = models.CharField(max_length=300, blank=True)
    kapa_standards = models.CharField(max_length=300, blank=True)
    test_image = models.ImageField(upload_to='test_images/', null=True, blank=True, default='test_images/default.jpg')
    lab_qc_comments = models.TextField(blank=True)
    tests_done_by = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Test Results {self.test_number}" if self.test_number else "New Test Results"

    class Meta:
        verbose_name_plural = "Test Results"

class QAOTestApproval(models.Model):
    request = models.OneToOneField(RMTRRequest, on_delete=models.CASCADE, related_name='qao_approval')
    qao_approved = models.BooleanField(default=False)
    qao_rejected = models.BooleanField(default=False)
    qao_comments = models.TextField(blank=True)
    qao_date_approved = models.DateTimeField(null=True, blank=True)
    qao_date_rejected = models.DateTimeField(null=True, blank=True)

class HODTestApproval(models.Model):
    request = models.OneToOneField(RMTRRequest, on_delete=models.CASCADE, related_name='hod_test_approval')
    hod_test_approved = models.BooleanField(default=False)
    hod_test_rejected = models.BooleanField(default=False)
    hod_test_comments = models.TextField(null=True, blank=True)
    hod_test_date_approved = models.DateTimeField(null=True, blank=True)
    hod_test_date_rejected = models.DateTimeField(null=True, blank=True)

class FMTestApproval(models.Model):
    request = models.OneToOneField(RMTRRequest, on_delete=models.CASCADE, related_name='fm_test_approval')
    fm_test_approved = models.BooleanField(default=False)
    fm_test_rejected = models.BooleanField(default=False)
    fm_test_comments = models.TextField(blank=True)
    fm_test_date_approved = models.DateTimeField(null=True, blank=True)
    fm_test_date_rejected = models.DateTimeField(null=True, blank=True)

class ManagementTestApproval(models.Model):
    request = models.OneToOneField(RMTRRequest, on_delete=models.CASCADE, related_name='management_test_approval')
    management_test_approved = models.BooleanField(default=False)
    management_test_rejected = models.BooleanField(default=False)
    management_test_comments = models.TextField(blank=True)
    management_test_date_approved = models.DateTimeField(null=True, blank=True)
    management_test_date_rejected = models.DateTimeField(null=True, blank=True)

class MilanTestApproval(models.Model):
    request = models.OneToOneField(RMTRRequest, on_delete=models.CASCADE, related_name='milan_test_approval')
    milan_approved = models.BooleanField(default=False)
    milan_rejected = models.BooleanField(default=False)
    milan_comments = models.TextField(blank=True)
    milan_date_approved = models.DateTimeField(null=True, blank=True)
    milan_date_rejected = models.DateTimeField(null=True, blank=True)

    def finalize_request(self):
        if self.milan_approved:
            self.request.status = "Completed"
            self.request.save()

class RawMaterialCategory(models.Model):
    CATEGORY_CHOICES = [
        ('food_raw', 'Food Raw Materials'),
        ('non_food_raw', 'Non Food Raw Materials'),
        ('packaging', 'Packaging Material'),
    ]
    name = models.CharField(max_length=500, choices=CATEGORY_CHOICES, unique=True)

    def __str__(self):
        return self.get_name_display()

class RawMaterialSubcategory(models.Model):
    name = models.CharField(max_length=500)
    category = models.ForeignKey('RawMaterialCategory', on_delete=models.CASCADE)

    def __str__(self):
        return self.name

class TestType(models.Model):
    name = models.CharField(max_length=500)
    subcategory = models.ForeignKey(RawMaterialSubcategory, on_delete=models.CASCADE, default=1)

    def __str__(self):
        return self.name

class RawMaterialTest(models.Model):
    subcategory = models.ForeignKey(RawMaterialSubcategory, on_delete=models.CASCADE)
    name = models.CharField(max_length=500)

    def __str__(self):
        return f"{self.name} - {self.subcategory}"

class Material(models.Model):
    MATERIAL_CHOICES = [
        ('Raw Material Food', 'Raw Material Food'),
        ('Raw Material Non Food', 'Raw Material Non Food'),
        ('Packaging Material', 'Packaging Material'),
    ]
    name = models.CharField(max_length=500, choices=MATERIAL_CHOICES)

    def __str__(self):
        return self.name

class SubCategory(models.Model):
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='subcategories')
    name = models.CharField(max_length=200)

    def __str__(self):
        return f'{self.material.name} - {self.name}'

    class Meta:
        verbose_name = "Material Sub-categorie"

class Test(models.Model):
    sub_category = models.ForeignKey(SubCategory, on_delete=models.CASCADE, related_name='tests')
    name = models.CharField(max_length=600)

    def __str__(self):
        return f'{self.sub_category.name} - {self.name}'

class RawMaterialType(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, default="Default description")

class PackingMaterialType(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, default="Default description")

class RMTR(models.Model):
    rmtr_no = models.CharField(max_length=20, unique=True)
    plant = models.CharField(max_length=100)
    hod = models.CharField(max_length=100)
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='pending')
    requested_by = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to='rmtr_images/', blank=True, null=True)
    justification = models.TextField()

    class Meta:
        ordering = ['-created_at']

    def generate_next_rmtr_no(self):
        current_year = timezone.now().year
        prefix = f"{current_year}-"
        last_instance = RMTR.objects.filter(date__year=current_year).order_by('-id').first()
        if last_instance:
            try:
                last_number = int(last_instance.rmtr_no.split('-')[1])
            except (IndexError, ValueError):
                last_number = 0
            next_number = last_number + 1
        else:
            next_number = 1
        return f"{prefix}{next_number:04d}"

    def clean(self):
        if not self.requested_by:
            raise ValidationError("The 'Requested by' field cannot be empty.")

    def save(self, *args, **kwargs):
        if not self.rmtr_no:
            self.rmtr_no = self.generate_next_rmtr_no()
        with transaction.atomic():
            self.clean()
            super().save(*args, **kwargs)

    def __str__(self):
        return self.rmtr_no

class TestResult(models.Model):
    report = models.ForeignKey(RMTRRequest, on_delete=models.CASCADE, null=True, blank=True)
    tests_carried_out = models.CharField(max_length=100, default='')
    sample_results = models.CharField(max_length=100, default='')
    raw_materials_result = models.CharField(max_length=100, default='')
    kapa_standards = models.CharField(max_length=100, default='')
    image = models.ImageField(upload_to='test_results_images/', null=True, blank=True)

    def __str__(self):
        return self.tests_carried_out

class RawMaterialTestReport(models.Model):
    rmtr_request = models.ForeignKey(RMTRRequest, on_delete=models.CASCADE, null=True, blank=True)
    test_type = models.ForeignKey('TestType', on_delete=models.CASCADE)
    tests_done_by = models.CharField(max_length=100)
    conclusion = models.TextField(null=True, blank=True)
    hod = models.CharField(max_length=100, default='Default Hod')
    hod_approval = models.BooleanField(default=False)
    hod_comments = models.TextField(null=True, blank=True)
    hod_approval_date = models.DateTimeField(null=True, blank=True)
    qao_approval = models.BooleanField(default=False)
    qao_comments = models.TextField(null=True, blank=True)
    qao_approval_date = models.DateTimeField(null=True, blank=True)
    factory_manager_approval = models.BooleanField(default=False)
    factory_manager_comments = models.TextField(null=True, blank=True)
    factory_manager_approval_date = models.DateTimeField(null=True, blank=True)
    head_of_operations_approval = models.BooleanField(default=False)
    head_of_operations_comments = models.TextField(null=True, blank=True)
    head_of_operations_approval_date = models.DateTimeField(null=True, blank=True)
    ceo_fd_approval = models.BooleanField(default=False)
    ceo_fd_comments = models.TextField(null=True, blank=True)
    ceo_fd_approval_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Test Report for {self.test_type.name} by {self.tests_done_by}"

class Pending_DataFetch(models.Model):
    rmtr_no = models.CharField(max_length=100)
    supplier = models.CharField(max_length=100)
    date = models.DateField()
    status = models.CharField(max_length=20)
    plant = models.CharField(max_length=20)

class ApprovalLogAdmin(admin.ModelAdmin):
    list_display = ('report_id', 'user', 'action', 'created_at', 'status_before', 'status_after')
    list_filter = ('action', 'created_at')
    search_fields = ('report__rmtr_no', 'imp_report__imp_rmtr_no', 'user__username', 'comments')
    readonly_fields = ('created_at',)

    def report_id(self, obj):
        return obj.report.rmtr_no if obj.report else obj.imp_report.imp_rmtr_no if obj.imp_report else 'Unknown'
    report_id.short_description = 'Report ID'

class SupplierAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

class RawMaterialTestReportAdmin(admin.ModelAdmin):
    list_display = ['get_rmtr_no', 'get_date', 'get_supplier', 'get_plant', 'get_material_type', 'get_test_type']
    list_filter = ['rmtr_request__date', 'rmtr_request__supplier', 'rmtr_request__plant', 'test_type']
    search_fields = ['rmtr_request__rmtr_no', 'rmtr_request__supplier__name', 'rmtr_request__plant__name', 'test_type__name']

    def get_rmtr_no(self, obj):
        return obj.rmtr_request.rmtr_no if obj.rmtr_request else 'Unlinked'
    def get_date(self, obj):
        return obj.rmtr_request.date if obj.rmtr_request else None
    def get_supplier(self, obj):
        return obj.rmtr_request.supplier.name if obj.rmtr_request else None
    def get_plant(self, obj):
        return obj.rmtr_request.plant.name if obj.rmtr_request else None
    def get_material_type(self, obj):
        return obj.rmtr_request.material_type if obj.rmtr_request else None
    def get_test_type(self, obj):
        return obj.test_type.name

    get_rmtr_no.short_description = 'RMTR No'
    get_date.short_description = 'Date'
    get_supplier.short_description = 'Supplier'
    get_plant.short_description = 'Plant'
    get_material_type.short_description = 'Material Type'
    get_test_type.short_description = 'Test Type'

class Report(models.Model):
    PENDING = 'pending'
    COMPLETED = 'completed'
    STATUS_CHOICES = [
        (PENDING, _('Pending')),
        (COMPLETED, _('Completed')),
    ]
    rmtr_no = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_created')
    modified_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_modified', null=True, blank=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.rmtr_no} - {self.title}"

    def is_completed(self):
        return self.status == self.COMPLETED

@receiver(pre_save, sender=RMTRRequest)
def log_rmtr_actions(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = RMTRRequest.objects.get(pk=instance.pk)
            if old_instance.status != instance.status:
                ApprovalLog.objects.create(
                    report=instance,
                    user=instance.last_status_changed_by or instance.current_user,
                    action='status_changed',
                    comments=f"Status changed from {old_instance.status} to {instance.status}",
                    status_before=old_instance.status,
                    status_after=instance.status,
                    ip_address=instance.current_user.profile.ip_address if hasattr(instance.current_user, 'profile') else None,
                    user_agent=instance.current_user.profile.user_agent if hasattr(instance.current_user, 'profile') else None
                )
            test_fields = [f'tests_carried_out{i}' for i in range(1, 17)] + [f'sample_results{i}' for i in range(1, 17)] + \
                          [f'raw_material_results{i}' for i in range(1, 17)] + [f'kapa_standards{i}' for i in range(1, 17)]
            changes = {}
            for field in test_fields:
                old_value = getattr(old_instance, field, None)
                new_value = getattr(instance, field, None)
                if old_value != new_value:
                    changes[field] = {'old': old_value, 'new': new_value}
            if changes:
                instance.test_results_modified_by = instance.current_user
                instance.test_results_modified_at = timezone.now()
                ApprovalLog.objects.create(
                    report=instance,
                    user=instance.current_user,
                    action='test_results_updated',
                    comments='Test results modified',
                    status_before=old_instance.status,
                    status_after=instance.status,
                    field_changes=changes,
                    #ip_address=instance.current_user.profile.ip_address if hasattr(instance.current_user, 'profile') else None,
                    user_agent=instance.current_user.profile.user_agent if hasattr(instance.current_user, 'profile') else None
                )
            approval_fields = [
                ('hod_purchase_approved', 'hod_purchase_by', 'hod_purchase_comments'),
                ('management_approved', 'management_by', 'management_comments'),
                ('management_approved_2', 'management_by_2', 'management_comments_2'),
                ('fm_approved', 'fm_by', 'fm_comments'),
                ('hod_approved', 'hod_by', 'hod_comments'),
                ('qao_approved', 'qao_by', 'qao_comments'),
                ('hod_test_approved', 'hod_test_by', 'hod_test_comments'),
                ('fm_test_approved', 'fm_test_by', 'fm_test_comments'),
                ('management_test_approved', 'management_test_by', 'management_test_comments'),
                ('milan_approved', 'milan_by', 'milan_comments')
            ]
            for approved_field, by_field, comment_field in approval_fields:
                old_approved = getattr(old_instance, approved_field)
                new_approved = getattr(instance, approved_field)
                old_rejected = getattr(old_instance, approved_field.replace('approved', 'rejected'))
                new_rejected = getattr(instance, approved_field.replace('approved', 'rejected'))
                if (old_approved != new_approved and new_approved) or (old_rejected != new_rejected and new_rejected):
                    action = 'approved' if new_approved else 'rejected'
                    comments = getattr(instance, comment_field, '')
                    ApprovalLog.objects.create(
                        report=instance,
                        user=getattr(instance, by_field),
                        action=action,
                        comments=comments,
                        status_before=old_instance.status,
                        status_after=instance.status,
                        ip_address=instance.current_user.profile.ip_address if hasattr(instance.current_user, 'profile') else None,
                        user_agent=instance.current_user.profile.user_agent if hasattr(instance.current_user, 'profile') else None
                    )
        except RMTRRequest.DoesNotExist:
            pass
    else:
        ApprovalLog.objects.create(
            report=instance,
            user=instance.created_by,
            action='created',
            comments='RMTR Request created',
            status_after=instance.status,
            ip_address=instance.created_by.profile.ip_address if hasattr(instance.created_by, 'profile') else None,
            user_agent=instance.created_by.profile.user_agent if hasattr(instance.created_by, 'profile') else None
        )

@receiver(pre_save, sender=IMP_RMTRRequest)
def log_imp_rmtr_actions(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = IMP_RMTRRequest.objects.get(pk=instance.pk)
            if old_instance.status != instance.status:
                ApprovalLog.objects.create(
                    imp_report=instance,
                    user=instance.last_status_changed_by or instance.current_user,
                    action='status_changed',
                    comments=f"Status changed from {old_instance.status} to {instance.status}",
                    status_before=old_instance.status,
                    status_after=instance.status,
                    ip_address=instance.current_user.profile.ip_address if hasattr(instance.current_user, 'profile') else None,
                    user_agent=instance.current_user.profile.user_agent if hasattr(instance.current_user, 'profile') else None
                )
            test_fields = [f'tests_carried_out{i}' for i in range(1, 17)] + [f'sample_results{i}' for i in range(1, 17)] + \
                          [f'raw_material_results{i}' for i in range(1, 17)] + [f'kapa_standards{i}' for i in range(1, 17)]
            changes = {}
            for field in test_fields:
                old_value = getattr(old_instance, field, None)
                new_value = getattr(instance, field, None)
                if old_value != new_value:
                    changes[field] = {'old': old_value, 'new': new_value}
            if changes:
                instance.test_results_modified_by = instance.current_user
                instance.test_results_modified_at = timezone.now()
                ApprovalLog.objects.create(
                    imp_report=instance,
                    user=instance.current_user,
                    action='test_results_updated',
                    comments='Test results modified',
                    status_before=old_instance.status,
                    status_after=instance.status,
                    field_changes=changes,
                    ip_address=instance.current_user.profile.ip_address if hasattr(instance.current_user, 'profile') else None,
                    user_agent=instance.current_user.profile.user_agent if hasattr(instance.current_user, 'profile') else None
                )
            approval_fields = [
                ('hod_purchase_approved', 'hod_purchase_by', 'hod_purchase_comments'),
                ('management_approved', 'management_by', 'management_comments'),
                ('management_approved_2', 'management_by_2', 'management_comments_2'),
                ('fm_approved', 'fm_by', 'fm_comments'),
                ('hod_approved', 'hod_by', 'hod_comments'),
                ('qao_approved', 'qao_by', 'qao_comments'),
                ('hod_test_approved', 'hod_test_by', 'hod_test_comments'),
                ('fm_test_approved', 'fm_test_by', 'fm_test_comments'),
                ('management_test_approved', 'management_test_by', 'management_test_comments'),
                ('milan_approved', 'milan_by', 'milan_comments')
            ]
            for approved_field, by_field, comment_field in approval_fields:
                old_approved = getattr(old_instance, approved_field)
                new_approved = getattr(instance, approved_field)
                old_rejected = getattr(old_instance, approved_field.replace('approved', 'rejected'))
                new_rejected = getattr(instance, approved_field.replace('approved', 'rejected'))
                if (old_approved != new_approved and new_approved) or (old_rejected != new_rejected and new_rejected):
                    action = 'approved' if new_approved else 'rejected'
                    comments = getattr(instance, comment_field, '')
                    ApprovalLog.objects.create(
                        imp_report=instance,
                        user=getattr(instance, by_field),
                        action=action,
                        comments=comments,
                        status_before=old_instance.status,
                        status_after=instance.status,
                        ip_address=instance.current_user.profile.ip_address if hasattr(instance.current_user, 'profile') else None,
                        user_agent=instance.current_user.profile.user_agent if hasattr(instance.current_user, 'profile') else None
                    )
        except IMP_RMTRRequest.DoesNotExist:
            pass
    else:
        ApprovalLog.objects.create(
            imp_report=instance,
            user=instance.created_by,
            action='created',
            comments='IMP RMTR Request created',
            status_after=instance.status,
            ip_address=instance.created_by.profile.ip_address if hasattr(instance.created_by, 'profile') else None,
            user_agent=instance.created_by.profile.user_agent if hasattr(instance.created_by, 'profile') else None
        )

@receiver(post_save, sender=RetestRequest)
def log_retest_request(sender, instance, created, **kwargs):
    if created:
        report_id = instance.rmtr_no.rmtr_no if instance.rmtr_no else instance.imp_rmtr_no.imp_rmtr_no if instance.imp_rmtr_no else 'Unknown'
        ApprovalLog.objects.create(
            report=instance.rmtr_no,
            imp_report=instance.imp_rmtr_no,
            user=instance.requested_by,
            action='retest_requested',
            comments=instance.comments,
            retest_reason=instance.reason,
            status_before=instance.original_status,
            status_after='Retest Requested',
            ip_address=instance.requested_by.profile.ip_address if hasattr(instance.requested_by, 'profile') else None,
            user_agent=instance.requested_by.profile.user_agent if hasattr(instance.requested_by, 'profile') else None
        )
    if instance.completed:
        ApprovalLog.objects.create(
            report=instance.rmtr_no,
            imp_report=instance.imp_rmtr_no,
            user=instance.requested_by,
            action='retest_completed',
            comments='Retest completed',
            status_before='Retest Requested',
            status_after=instance.original_status,
            field_changes=instance.test_data,
            ip_address=instance.requested_by.profile.ip_address if hasattr(instance.requested_by, 'profile') else None,
            user_agent=instance.requested_by.profile.user_agent if hasattr(instance.requested_by, 'profile') else None
        )

admin.site.register(ApprovalLog, ApprovalLogAdmin)
admin.site.register(Supplier, SupplierAdmin)
admin.site.register(RawMaterialTestReport, RawMaterialTestReportAdmin)