from django import forms
from django.forms import inlineformset_factory

from .models import (
    ArtworkRequest, ArtworkLogoCheck, ArtworkColorSpec,
    CHECK_STATUS_CHOICES, LOGO_STATUS_CHOICES, LogoTemplate, ProductCategory, PackagingSupplier,
)


APPROVAL_EXCLUDE = [
    'artwork_no', 'date_created', 'created_by', 'current_user', 'status',
    'last_status_change', 'last_status_changed_by', 'last_reminder_sent',
    'marketing_approved', 'marketing_rejected', 'marketing_comments',
    'marketing_date_approved', 'marketing_date_rejected', 'marketing_by',
    'qa_approved', 'qa_rejected', 'qa_comments',
    'qa_date_approved', 'qa_date_rejected', 'qa_by',
    'operations_hod_approved', 'operations_hod_rejected', 'operations_hod_comments',
    'operations_hod_date_approved', 'operations_hod_date_rejected', 'operations_hod_by',
    'product_dev_approved', 'product_dev_rejected', 'product_dev_comments',
    'product_dev_date_approved', 'product_dev_date_rejected', 'product_dev_by',
    'milan_approved', 'milan_rejected', 'milan_comments',
    'milan_date_approved', 'milan_date_rejected', 'milan_by',
    'is_rejected', 'rejected_by', 'rejection_stage', 'rejection_date',
    'rejection_comments', 'revision_count',
    'sap_material_description', 'sap_material_code',
    'procurement_filled_by', 'procurement_filled_date',
]


class ArtworkRequestForm(forms.ModelForm):
    new_product_category = forms.CharField(
        required=False,
        label='New category',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'New category name',
        }),
    )
    new_packaging_supplier = forms.CharField(
        required=False,
        label='New supplier',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'New supplier name',
        }),
    )

    class Meta:
        model = ArtworkRequest
        exclude = APPROVAL_EXCLUDE
        widgets = {
            'reason_for_update': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'ingredients': forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}),
            'product_name': forms.TextInput(attrs={'class': 'form-control'}),
            'sku_size': forms.TextInput(attrs={'class': 'form-control'}),
            'kebs_number': forms.TextInput(attrs={'class': 'form-control'}),
            'artwork_size': forms.TextInput(attrs={'class': 'form-control'}),
            'dimensions_packaging': forms.TextInput(attrs={'class': 'form-control'}),
            'eye_mark_size': forms.TextInput(attrs={'class': 'form-control'}),
            'print_type': forms.TextInput(attrs={'class': 'form-control'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control'}),
            'unwinding_direction': forms.TextInput(attrs={'class': 'form-control'}),
            'lamination': forms.TextInput(attrs={'class': 'form-control'}),
            'logo_size_status': forms.Select(attrs={'class': 'form-control'}),
            'brand_text_status': forms.Select(attrs={'class': 'form-control'}),
            'r_mark_status': forms.Select(attrs={'class': 'form-control'}),
            'number_of_colors': forms.NumberInput(attrs={'class': 'form-control'}),
            'not_hydrogenated_text': forms.Select(attrs={'class': 'form-control'}),
            'net_weight_e': forms.Select(attrs={'class': 'form-control'}),
            'pre_printed_expiry': forms.Select(attrs={'class': 'form-control'}),
            'fortification_text': forms.Select(attrs={'class': 'form-control'}),
            'nema_requirements': forms.Select(attrs={'class': 'form-control'}),
            'triple_refined': forms.Select(attrs={'class': 'form-control'}),
            'storage_condition': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_lookup_field(
            'product_category', ProductCategory, '— Select category —',
        )
        self._setup_lookup_field(
            'packaging_supplier', PackagingSupplier, '— Select supplier —',
        )

    def _setup_lookup_field(self, field_name, model_class, empty_label):
        items = model_class.objects.filter(is_active=True).order_by('display_order', 'name')
        choices = [('', empty_label)]
        choices += [(item.name, item.name) for item in items]
        current = ''
        if self.instance.pk:
            current = getattr(self.instance, field_name, '') or ''
            if current and current not in [choice[0] for choice in choices if choice[0]]:
                choices.append((current, current))
        self.fields[field_name] = forms.ChoiceField(
            choices=choices,
            required=False,
            initial=current,
            widget=forms.Select(attrs={'class': 'form-control'}),
        )

    def _resolve_lookup_value(self, cleaned, field_name, new_field_name, model_class):
        new_value = (cleaned.get(new_field_name) or '').strip()
        selected = (cleaned.get(field_name) or '').strip()
        if new_value:
            existing = model_class.objects.filter(name__iexact=new_value).first()
            if not existing:
                existing = model_class.objects.create(name=new_value)
            cleaned[field_name] = existing.name
        elif selected:
            existing = model_class.objects.filter(name__iexact=selected).first()
            if not existing:
                model_class.objects.create(name=selected)
            cleaned[field_name] = selected
        else:
            cleaned[field_name] = ''

    def clean(self):
        cleaned = super().clean()
        self._resolve_lookup_value(
            cleaned, 'product_category', 'new_product_category', ProductCategory,
        )
        self._resolve_lookup_value(
            cleaned, 'packaging_supplier', 'new_packaging_supplier', PackagingSupplier,
        )
        if getattr(self, 'is_submitting', False):
            if not (cleaned.get('product_name') or '').strip():
                self.add_error(
                    'product_name',
                    'Product name is required before submitting for approval.',
                )
        return cleaned


class LogoCheckForm(forms.ModelForm):
    class Meta:
        model = ArtworkLogoCheck
        fields = ['logo_name', 'status', 'colors_used']
        widgets = {
            'logo_name': forms.HiddenInput(),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'colors_used': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Pantone 273 C'}),
        }


class ColorSpecForm(forms.ModelForm):
    class Meta:
        model = ArtworkColorSpec
        fields = ['slot_number', 'color_name', 'cmyk_values', 'color_swatch']
        widgets = {
            'slot_number': forms.HiddenInput(),
            'color_name': forms.TextInput(attrs={'class': 'form-control'}),
            'cmyk_values': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'C(100) M(0) Y(0) K(0)'}),
            'color_swatch': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }


LogoCheckFormSet = inlineformset_factory(
    ArtworkRequest, ArtworkLogoCheck, form=LogoCheckForm,
    extra=0, can_delete=False,
)

ColorSpecFormSet = inlineformset_factory(
    ArtworkRequest, ArtworkColorSpec, form=ColorSpecForm,
    extra=0, can_delete=False,
)


class StageApprovalForm(forms.Form):
    comments = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control', 'required': True}),
        required=True,
        label='Comments',
    )


class ProcurementForm(forms.ModelForm):
    class Meta:
        model = ArtworkRequest
        fields = ['sap_material_description', 'sap_material_code']
        widgets = {
            'sap_material_description': forms.TextInput(attrs={'class': 'form-control'}),
            'sap_material_code': forms.TextInput(attrs={'class': 'form-control'}),
        }


class LogoTemplateForm(forms.ModelForm):
    """Designers upload reusable logo images for the artwork form."""

    class Meta:
        model = LogoTemplate
        fields = ['name', 'icon', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Halal, KEBS, Recycling',
            }),
            'icon': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/png,image/jpeg,image/gif,image/webp,image/svg+xml',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, require_icon=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_icon = require_icon
        self.fields['name'].required = True
        if not require_icon:
            self.fields['icon'].required = False
            self.fields['icon'].help_text = 'Leave blank to keep the current image.'

    def clean_icon(self):
        icon = self.cleaned_data.get('icon')
        if not icon and self.require_icon and not (self.instance and self.instance.icon):
            raise forms.ValidationError('Please upload a logo image.')
        if icon:
            allowed = {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/svg+xml'}
            content_type = getattr(icon, 'content_type', '') or ''
            if content_type and content_type not in allowed:
                raise forms.ValidationError('Upload a PNG, JPG, GIF, WebP, or SVG image.')
            if icon.size > 5 * 1024 * 1024:
                raise forms.ValidationError('Image must be 5 MB or smaller.')
        return icon

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if not name:
            raise forms.ValidationError('Logo name is required.')
        qs = LogoTemplate.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('A logo with this name already exists.')
        return name


class LogoTemplateCreateForm(LogoTemplateForm):
    """Add new logo — name and image only."""

    class Meta(LogoTemplateForm.Meta):
        fields = ['name', 'icon']

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.is_active = True
        if commit:
            instance.save()
        return instance
