from django.contrib import admin
from django.utils.html import format_html

from .models import (
    LogoTemplate, ProductCategory, PackagingSupplier, ArtworkRequest, ArtworkLogoCheck, ArtworkColorSpec,
    ArtworkAttachment, ArtworkApprovalLog,
)


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'hod', 'deputy_hod', 'display_order', 'is_active', 'created_at',
    ]
    list_editable = ['display_order', 'is_active']
    list_filter = ['is_active', 'hod', 'deputy_hod']
    search_fields = [
        'name',
        'hod__username', 'hod__first_name', 'hod__last_name', 'hod__email',
        'deputy_hod__username', 'deputy_hod__first_name', 'deputy_hod__last_name',
        'deputy_hod__email',
    ]
    ordering = ['display_order', 'name']
    autocomplete_fields = ['hod', 'deputy_hod']
    fields = ['name', 'hod', 'deputy_hod', 'display_order', 'is_active']
    list_select_related = ['hod', 'deputy_hod']


@admin.register(PackagingSupplier)
class PackagingSupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'display_order', 'is_active', 'created_at']
    list_editable = ['display_order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']
    ordering = ['display_order', 'name']
    fields = ['name', 'display_order', 'is_active']


@admin.register(LogoTemplate)
class LogoTemplateAdmin(admin.ModelAdmin):
    list_display = ['icon_preview', 'name', 'display_order', 'is_active']
    list_editable = ['display_order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']
    ordering = ['display_order', 'name']
    fields = ['name', 'icon', 'icon_preview_large', 'display_order', 'is_active']
    readonly_fields = ['icon_preview_large']

    @admin.display(description='Icon')
    def icon_preview(self, obj):
        if obj.icon:
            return format_html(
                '<img src="{}" width="40" height="40" style="object-fit:contain;border-radius:4px;" alt="">',
                obj.icon.url,
            )
        return '—'

    @admin.display(description='Preview')
    def icon_preview_large(self, obj):
        if obj.icon:
            return format_html(
                '<img src="{}" width="120" height="120" style="object-fit:contain;border:1px solid #ddd;padding:8px;" alt="">',
                obj.icon.url,
            )
        return 'Upload an image — it will appear as a clickable logo on the artwork form.'


class ArtworkLogoCheckInline(admin.TabularInline):
    model = ArtworkLogoCheck
    extra = 0
    readonly_fields = ['logo_template']


class ArtworkColorSpecInline(admin.TabularInline):
    model = ArtworkColorSpec
    extra = 0


class ArtworkAttachmentInline(admin.TabularInline):
    model = ArtworkAttachment
    extra = 0
    readonly_fields = ['uploaded_at', 'file_size', 'mime_type']


@admin.register(ArtworkRequest)
class ArtworkRequestAdmin(admin.ModelAdmin):
    list_display = [
        'artwork_no', 'product_name', 'sku_size', 'status',
        'created_by', 'date_created', 'revision_count',
    ]
    search_fields = ['artwork_no', 'product_name', 'sku_size', 'barcode']
    list_filter = ['status', 'product_category', 'is_rejected']
    readonly_fields = ['artwork_no', 'date_created']
    inlines = [ArtworkLogoCheckInline, ArtworkColorSpecInline, ArtworkAttachmentInline]


@admin.register(ArtworkAttachment)
class ArtworkAttachmentAdmin(admin.ModelAdmin):
    list_display = [
        'artwork_request', 'original_filename', 'file_type',
        'is_primary', 'uploaded_by', 'uploaded_at', 'file_size',
    ]
    list_filter = ['file_type', 'is_primary']


@admin.register(ArtworkApprovalLog)
class ArtworkApprovalLogAdmin(admin.ModelAdmin):
    list_display = [
        'artwork_request', 'user', 'action', 'stage',
        'status_before', 'status_after', 'timestamp',
    ]
    list_filter = ['action', 'stage']
    readonly_fields = [
        'artwork_request', 'user', 'action', 'stage', 'comments',
        'status_before', 'status_after', 'timestamp', 'ip_address',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
