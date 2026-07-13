from django.conf import settings
from django.db import models
from django.contrib.auth.models import User

from .color_utils import cmyk_to_hex


CHECK_STATUS_CHOICES = [
    ('Okay', 'Okay'),
    ('N/A', 'N/A'),
    ('Check', 'Check'),
]

LOGO_STATUS_CHOICES = [
    ('Okay', 'Okay'),
    ('N/A', 'N/A'),
]

FILE_TYPE_CHOICES = [
    ('artwork_image', 'Artwork Image'),
    ('pdf', 'PDF'),
    ('reference', 'Reference'),
]

ACTION_CHOICES = [
    ('created', 'Created'),
    ('submitted', 'Submitted'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('revised', 'Revised'),
    ('resubmitted', 'Resubmitted'),
]


class LogoTemplate(models.Model):
    """Reusable logo/symbol definitions designers tick during artwork creation."""
    name = models.CharField(max_length=100, unique=True)
    icon = models.ImageField(upload_to='artwork/logo_icons/', blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class ProductCategory(models.Model):
    """User-managed product categories for the artwork form dropdown."""
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name_plural = 'Product categories'

    def __str__(self):
        return self.name


class PackagingSupplier(models.Model):
    """User-managed packaging suppliers for the artwork form dropdown."""
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name_plural = 'Packaging suppliers'

    def __str__(self):
        return self.name


class ArtworkRequest(models.Model):
    artwork_no = models.CharField(max_length=20, unique=True, db_index=True)
    date_created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='artworks_created'
    )
    current_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='artworks_assigned'
    )
    status = models.CharField(max_length=80, default='Design Created')
    last_status_change = models.DateTimeField(auto_now=True)
    last_status_changed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='artwork_status_changes'
    )
    last_reminder_sent = models.DateTimeField(null=True, blank=True)
    reason_for_update = models.TextField(blank=True)

    # Product details
    product_category = models.CharField(max_length=100, blank=True)
    product_name = models.CharField(max_length=200, blank=True, default='')
    sku_size = models.CharField(max_length=100, blank=True)
    kebs_number = models.CharField(max_length=50, blank=True)
    artwork_size = models.CharField(max_length=50, blank=True)
    dimensions_packaging = models.CharField(max_length=50, blank=True)
    eye_mark_size = models.CharField(max_length=50, blank=True)
    print_type = models.CharField(max_length=50, blank=True)
    barcode = models.CharField(max_length=50, blank=True)
    unwinding_direction = models.CharField(max_length=50, blank=True)
    packaging_supplier = models.CharField(max_length=100, blank=True)
    lamination = models.CharField(max_length=200, blank=True)

    # Product logo checks
    logo_size_status = models.CharField(max_length=10, choices=CHECK_STATUS_CHOICES, blank=True)
    brand_text_status = models.CharField(max_length=10, choices=CHECK_STATUS_CHOICES, blank=True)
    r_mark_status = models.CharField(max_length=10, choices=CHECK_STATUS_CHOICES, blank=True)
    number_of_colors = models.PositiveIntegerField(null=True, blank=True)

    # Artwork text checks
    not_hydrogenated_text = models.CharField(max_length=10, choices=LOGO_STATUS_CHOICES, blank=True)
    net_weight_e = models.CharField(max_length=10, choices=LOGO_STATUS_CHOICES, blank=True)
    pre_printed_expiry = models.CharField(max_length=10, choices=LOGO_STATUS_CHOICES, blank=True)
    fortification_text = models.CharField(max_length=10, choices=LOGO_STATUS_CHOICES, blank=True)
    nema_requirements = models.CharField(max_length=10, choices=LOGO_STATUS_CHOICES, blank=True)
    triple_refined = models.CharField(max_length=10, choices=LOGO_STATUS_CHOICES, blank=True)
    storage_condition = models.CharField(max_length=10, choices=LOGO_STATUS_CHOICES, blank=True)

    # Kapa requirements
    ingredients = models.TextField(blank=True)

    # Procurement (post-approval)
    sap_material_description = models.CharField(max_length=255, blank=True)
    sap_material_code = models.CharField(max_length=100, blank=True)
    procurement_filled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='artworks_procurement'
    )
    procurement_filled_date = models.DateTimeField(null=True, blank=True)

    # Stage approvals
    marketing_approved = models.BooleanField(default=False)
    marketing_rejected = models.BooleanField(default=False)
    marketing_comments = models.TextField(blank=True)
    marketing_date_approved = models.DateTimeField(null=True, blank=True)
    marketing_date_rejected = models.DateTimeField(null=True, blank=True)
    marketing_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='marketing_approvals'
    )

    qa_approved = models.BooleanField(default=False)
    qa_rejected = models.BooleanField(default=False)
    qa_comments = models.TextField(blank=True)
    qa_date_approved = models.DateTimeField(null=True, blank=True)
    qa_date_rejected = models.DateTimeField(null=True, blank=True)
    qa_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='qa_approvals'
    )

    operations_hod_approved = models.BooleanField(default=False)
    operations_hod_rejected = models.BooleanField(default=False)
    operations_hod_comments = models.TextField(blank=True)
    operations_hod_date_approved = models.DateTimeField(null=True, blank=True)
    operations_hod_date_rejected = models.DateTimeField(null=True, blank=True)
    operations_hod_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='operations_approvals'
    )

    product_dev_approved = models.BooleanField(default=False)
    product_dev_rejected = models.BooleanField(default=False)
    product_dev_comments = models.TextField(blank=True)
    product_dev_date_approved = models.DateTimeField(null=True, blank=True)
    product_dev_date_rejected = models.DateTimeField(null=True, blank=True)
    product_dev_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='product_dev_approvals'
    )

    milan_approved = models.BooleanField(default=False)
    milan_rejected = models.BooleanField(default=False)
    milan_comments = models.TextField(blank=True)
    milan_date_approved = models.DateTimeField(null=True, blank=True)
    milan_date_rejected = models.DateTimeField(null=True, blank=True)
    milan_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='milan_approvals'
    )

    # Rejection tracking
    is_rejected = models.BooleanField(default=False)
    rejected_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='artwork_rejections'
    )
    rejection_stage = models.CharField(max_length=50, blank=True)
    rejection_date = models.DateTimeField(null=True, blank=True)
    rejection_comments = models.TextField(blank=True)
    revision_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-date_created']

    def __str__(self):
        return f'{self.artwork_no} - {self.product_name}'

    @property
    def primary_attachment(self):
        return self.attachments.filter(is_primary=True).first() or self.attachments.first()


class ArtworkLogoCheck(models.Model):
    artwork_request = models.ForeignKey(
        ArtworkRequest, on_delete=models.CASCADE, related_name='logo_checks'
    )
    logo_template = models.ForeignKey(
        LogoTemplate, on_delete=models.SET_NULL, null=True, blank=True
    )
    logo_name = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=LOGO_STATUS_CHOICES, blank=True)
    colors_used = models.CharField(max_length=200, blank=True)
    logo_image = models.ImageField(upload_to='artwork/logo_swatches/', blank=True, null=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.logo_name} ({self.artwork_request.artwork_no})'


class ArtworkColorSpec(models.Model):
    artwork_request = models.ForeignKey(
        ArtworkRequest, on_delete=models.CASCADE, related_name='color_specs'
    )
    slot_number = models.PositiveIntegerField()
    color_name = models.CharField(max_length=100, blank=True)
    cmyk_values = models.CharField(max_length=100, blank=True)
    color_hex = models.CharField(max_length=7, blank=True)
    color_swatch = models.ImageField(upload_to='artwork/color_swatches/', blank=True, null=True)

    class Meta:
        ordering = ['slot_number']
        unique_together = [['artwork_request', 'slot_number']]

    def __str__(self):
        return f'Slot {self.slot_number}: {self.color_name}'

    @property
    def swatch_color(self):
        """Stored hex color, falling back to one computed from the CMYK values."""
        return self.color_hex or cmyk_to_hex(self.cmyk_values)

    @property
    def has_content(self):
        return bool(self.color_name or self.cmyk_values or self.color_hex or self.color_swatch)


def artwork_upload_path(instance, filename):
    return f'artwork/{instance.artwork_request.artwork_no}/{filename}'


class ArtworkAttachment(models.Model):
    artwork_request = models.ForeignKey(
        ArtworkRequest, on_delete=models.CASCADE, related_name='attachments'
    )
    file = models.FileField(upload_to=artwork_upload_path)
    original_filename = models.CharField(max_length=255, blank=True)
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES, default='artwork_image')
    description = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_primary = models.BooleanField(default=False)
    file_size = models.PositiveBigIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-is_primary', '-uploaded_at']

    def __str__(self):
        return self.original_filename or self.file.name

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            self.original_filename = self.file.name.split('/')[-1]
        if self.file and hasattr(self.file, 'size'):
            self.file_size = self.file.size
        super().save(*args, **kwargs)
        if self.is_primary:
            ArtworkAttachment.objects.filter(
                artwork_request=self.artwork_request
            ).exclude(pk=self.pk).update(is_primary=False)


class ArtworkApprovalLog(models.Model):
    artwork_request = models.ForeignKey(
        ArtworkRequest, on_delete=models.CASCADE, related_name='approval_logs'
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    stage = models.CharField(max_length=50, blank=True)
    comments = models.TextField(blank=True)
    status_before = models.CharField(max_length=80, blank=True)
    status_after = models.CharField(max_length=80, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.artwork_request.artwork_no} - {self.action}'
