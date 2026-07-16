import re

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

FIELD_UI = {
    'reason_for_update': {
        'label': 'Reason for Update',
        'placeholder': 'Why is this artwork being created or revised?',
        'help_text': 'Brief context for approvers (new SKU, regulatory change, redesign, etc.).',
    },
    'product_name': {
        'label': 'Product Name',
        'placeholder': 'e.g. Classic Cooking Oil',
        'help_text': 'Required when submitting for approval.',
        'autocomplete': 'off',
    },
    'sku_size': {
        'label': 'SKU / Size',
        'placeholder': 'e.g. 500 ml · Wrapper',
        'help_text': 'Pack size and format as it appears on the brief.',
    },
    'kebs_number': {
        'label': 'KEBS Number',
        'placeholder': 'e.g. KS EAS 38',
        'help_text': 'Kenya Bureau of Standards reference, if applicable.',
    },
    'artwork_size': {
        'label': 'Artwork Size',
        'placeholder': 'e.g. 280 × 185 mm',
    },
    'dimensions_packaging': {
        'label': 'Packaging Dimensions',
        'placeholder': 'e.g. W × H × D (mm)',
    },
    'eye_mark_size': {
        'label': 'Eye Mark Size',
        'placeholder': 'e.g. 4 × 8 mm',
    },
    'print_type': {
        'label': 'Print Type',
        'placeholder': 'e.g. Gravure, Flexo',
        'list': 'print-type-suggestions',
    },
    'barcode': {
        'label': 'Barcode',
        'placeholder': 'EAN-13, UPC-A, or EAN-8',
        'help_text': 'Digits only; check digit is validated when provided.',
        'inputmode': 'numeric',
        'autocomplete': 'off',
    },
    'unwinding_direction': {
        'label': 'Unwinding Direction',
        'placeholder': 'e.g. Position 1',
        'list': 'unwinding-suggestions',
    },
    'lamination': {
        'label': 'Lamination',
        'placeholder': 'e.g. PET / PE · Matte',
    },
    'number_of_colors': {
        'label': 'Number of Colors',
        'placeholder': 'e.g. 6',
        'help_text': 'Total print colors including specials (0–24).',
        'min': 0,
        'max': 24,
    },
    'ingredients': {
        'label': 'Ingredients',
        'placeholder': 'List ingredients in descending order. Put allergens in CAPITALS.',
        'help_text': 'Use CAPITALS for allergens so they stand out for QA review.',
    },
    'logo_size_status': {'label': 'Logo Size'},
    'brand_text_status': {'label': 'Brand Text'},
    'r_mark_status': {'label': '® Mark'},
    'not_hydrogenated_text': {'label': 'Not Hydrogenated Text'},
    'net_weight_e': {'label': 'Net Weight “e” Mark'},
    'pre_printed_expiry': {'label': 'Pre-Printed Expiry / BB Date'},
    'fortification_text': {'label': 'Fortification Text'},
    'nema_requirements': {'label': 'NEMA Requirements'},
    'triple_refined': {'label': 'Triple Refined'},
    'storage_condition': {'label': 'Storage Condition'},
}


def _gtin_check_digit_valid(digits: str) -> bool:
    """Validate GTIN / EAN / UPC check digit (mod-10)."""
    if not digits.isdigit() or len(digits) not in (8, 12, 13, 14):
        return False
    body, check = digits[:-1], int(digits[-1])
    total = 0
    # Right-to-left: odd positions ×3, even ×1 (GTIN weighting)
    for i, ch in enumerate(reversed(body)):
        n = int(ch)
        total += n * 3 if i % 2 == 0 else n
    return (10 - (total % 10)) % 10 == check


class ArtworkRequestForm(forms.ModelForm):
    new_product_category = forms.CharField(
        required=False,
        label='New category',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Type a new category name',
            'autocomplete': 'off',
        }),
    )
    new_packaging_supplier = forms.CharField(
        required=False,
        label='New supplier',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Type a new supplier name',
            'autocomplete': 'off',
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

    def __init__(self, *args, is_submitting=False, **kwargs):
        self.is_submitting = is_submitting
        super().__init__(*args, **kwargs)
        self._setup_lookup_field(
            'product_category', ProductCategory, '— Select category —',
        )
        self._setup_lookup_field(
            'packaging_supplier', PackagingSupplier, '— Select supplier —',
        )
        self._apply_field_ui()
        self._polish_choice_fields()

    def _apply_field_ui(self):
        for name, meta in FIELD_UI.items():
            field = self.fields.get(name)
            if not field:
                continue
            if meta.get('label'):
                field.label = meta['label']
            if meta.get('help_text'):
                field.help_text = meta['help_text']
            attrs = field.widget.attrs
            if meta.get('placeholder'):
                attrs['placeholder'] = meta['placeholder']
            if meta.get('autocomplete'):
                attrs['autocomplete'] = meta['autocomplete']
            if meta.get('inputmode'):
                attrs['inputmode'] = meta['inputmode']
            if meta.get('list'):
                attrs['list'] = meta['list']
            if 'min' in meta:
                attrs['min'] = str(meta['min'])
            if 'max' in meta:
                attrs['max'] = str(meta['max'])
            attrs.setdefault('class', 'form-control')

        # Max lengths from model
        for name, field in self.fields.items():
            model_field = getattr(ArtworkRequest, name, None)
            if model_field is None:
                continue
            try:
                max_length = model_field.field.max_length
            except Exception:
                max_length = None
            if max_length and hasattr(field.widget, 'attrs'):
                field.widget.attrs.setdefault('maxlength', str(max_length))

        self.fields['product_name'].required = False
        if self.is_submitting:
            self.fields['product_name'].widget.attrs['aria-required'] = 'true'

    def _polish_choice_fields(self):
        status_fields = [
            'logo_size_status', 'brand_text_status', 'r_mark_status',
            'not_hydrogenated_text', 'net_weight_e', 'pre_printed_expiry',
            'fortification_text', 'nema_requirements', 'triple_refined',
            'storage_condition',
        ]
        for name in status_fields:
            field = self.fields.get(name)
            if not field:
                continue
            field.required = False
            # Ensure a clear empty option
            choices = list(field.choices)
            if not choices or choices[0][0] != '':
                field.choices = [('', '— Select —')] + [
                    c for c in choices if c[0] != ''
                ]
            elif choices[0][1] in ('---------', ''):
                field.choices = [('', '— Select —')] + list(choices[1:])

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
            label='Product Category' if field_name == 'product_category' else 'Packaging Supplier',
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

    def clean_product_name(self):
        return (self.cleaned_data.get('product_name') or '').strip()

    def clean_sku_size(self):
        return (self.cleaned_data.get('sku_size') or '').strip()

    def clean_kebs_number(self):
        return (self.cleaned_data.get('kebs_number') or '').strip()

    def clean_artwork_size(self):
        return (self.cleaned_data.get('artwork_size') or '').strip()

    def clean_dimensions_packaging(self):
        return (self.cleaned_data.get('dimensions_packaging') or '').strip()

    def clean_eye_mark_size(self):
        return (self.cleaned_data.get('eye_mark_size') or '').strip()

    def clean_print_type(self):
        return (self.cleaned_data.get('print_type') or '').strip()

    def clean_unwinding_direction(self):
        return (self.cleaned_data.get('unwinding_direction') or '').strip()

    def clean_lamination(self):
        return (self.cleaned_data.get('lamination') or '').strip()

    def clean_ingredients(self):
        return (self.cleaned_data.get('ingredients') or '').strip()

    def clean_reason_for_update(self):
        return (self.cleaned_data.get('reason_for_update') or '').strip()

    def clean_barcode(self):
        raw = (self.cleaned_data.get('barcode') or '').strip()
        if not raw:
            return ''
        digits = re.sub(r'\D', '', raw)
        if not digits:
            raise forms.ValidationError('Barcode must contain digits.')
        if len(digits) not in (8, 12, 13, 14):
            raise forms.ValidationError(
                'Enter a valid barcode length (EAN-8, UPC-A, EAN-13, or GTIN-14).'
            )
        if not _gtin_check_digit_valid(digits):
            raise forms.ValidationError(
                'Barcode check digit is invalid. Please verify the number.'
            )
        return digits

    def clean_number_of_colors(self):
        value = self.cleaned_data.get('number_of_colors')
        if value is None or value == '':
            return None
        if value < 0 or value > 24:
            raise forms.ValidationError('Number of colors must be between 0 and 24.')
        return value

    def clean(self):
        cleaned = super().clean()
        self._resolve_lookup_value(
            cleaned, 'product_category', 'new_product_category', ProductCategory,
        )
        self._resolve_lookup_value(
            cleaned, 'packaging_supplier', 'new_packaging_supplier', PackagingSupplier,
        )
        if self.is_submitting:
            if not (cleaned.get('product_name') or '').strip():
                self.add_error(
                    'product_name',
                    'Product name is required before submitting for approval.',
                )
            if not (cleaned.get('product_category') or '').strip():
                self.add_error(
                    'product_category',
                    'Product category is required before submitting for approval.',
                )
        return cleaned


class LogoCheckForm(forms.ModelForm):
    class Meta:
        model = ArtworkLogoCheck
        fields = ['logo_name', 'status', 'colors_used']
        widgets = {
            'logo_name': forms.HiddenInput(),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'colors_used': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Pantone 273 C',
            }),
        }


class ColorSpecForm(forms.ModelForm):
    class Meta:
        model = ArtworkColorSpec
        fields = ['slot_number', 'color_name', 'cmyk_values', 'color_swatch']
        widgets = {
            'slot_number': forms.HiddenInput(),
            'color_name': forms.TextInput(attrs={'class': 'form-control'}),
            'cmyk_values': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'C(100) M(0) Y(0) K(0)',
            }),
            'color_swatch': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
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
        widget=forms.Textarea(attrs={
            'rows': 4,
            'class': 'form-control',
            'placeholder': 'Add clear approval or rejection comments for the designer…',
            'required': True,
        }),
        required=True,
        label='Comments',
        help_text='Required. Approvers: note what was reviewed. Rejectors: be specific.',
    )


class ProcurementForm(forms.ModelForm):
    class Meta:
        model = ArtworkRequest
        fields = ['sap_material_description', 'sap_material_code']
        labels = {
            'sap_material_description': 'SAP Material Description',
            'sap_material_code': 'SAP Material Code',
        }
        widgets = {
            'sap_material_description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'As registered in SAP',
                'autocomplete': 'off',
            }),
            'sap_material_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 10001234',
                'autocomplete': 'off',
            }),
        }

    def clean_sap_material_description(self):
        return (self.cleaned_data.get('sap_material_description') or '').strip()

    def clean_sap_material_code(self):
        return (self.cleaned_data.get('sap_material_code') or '').strip()


class LogoTemplateForm(forms.ModelForm):
    """Designers upload reusable logo images for the artwork form."""

    class Meta:
        model = LogoTemplate
        fields = ['name', 'icon', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Halal, KEBS, Recycling',
                'autocomplete': 'off',
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
        self.fields['name'].label = 'Logo Name'
        self.fields['icon'].label = 'Logo Image'
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
