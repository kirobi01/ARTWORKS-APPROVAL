"""Helpers for building artwork approval PDF context."""
import base64
from io import BytesIO


def _filled(value):
    return bool(value is not None and str(value).strip())


def encode_image_srgb_b64(file_field):
    """Return ``(base64_str, mime_type)`` for an image normalized to sRGB.

    wkhtmltopdf (QtWebKit) ignores embedded ICC color profiles and mishandles
    CMYK JPEGs, which makes embedded artwork look very different from the
    original. We open the image with Pillow, convert it to sRGB RGB (applying
    any embedded profile), flatten transparency onto white, and re-encode as a
    high-quality JPEG so the PDF matches what the user sees on screen.

    Falls back to the raw bytes when Pillow cannot read the file (e.g. SVG).
    """
    try:
        from PIL import Image, ImageCms

        with file_field.open('rb') as handle:
            raw = handle.read()
        image = Image.open(BytesIO(raw))
        image.load()
        icc_profile = image.info.get('icc_profile')

        def _apply_srgb(img):
            if not icc_profile:
                return img.convert('RGB')
            try:
                src_profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
                dst_profile = ImageCms.createProfile('sRGB')
                return ImageCms.profileToProfile(
                    img, src_profile, dst_profile, outputMode='RGB',
                )
            except Exception:
                return img.convert('RGB')

        if image.mode == 'CMYK':
            image = _apply_srgb(image)
        elif image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGBA')
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        else:
            image = _apply_srgb(image)

        buffer = BytesIO()
        image.save(buffer, format='JPEG', quality=95, subsampling=0)
        return base64.b64encode(buffer.getvalue()).decode(), 'image/jpeg'
    except Exception:
        try:
            with file_field.open('rb') as handle:
                return base64.b64encode(handle.read()).decode(), ''
        except Exception:
            return '', ''


def build_product_detail_rows(artwork):
    rows = [
        ('Product Category', artwork.product_category),
        ('Product Name', artwork.product_name),
        ('SKU Size', artwork.sku_size),
        ('KEBS Number', artwork.kebs_number),
        ('Artwork Size', artwork.artwork_size),
        ('Dimensions Packaging', artwork.dimensions_packaging),
        ('Eye Mark Size', artwork.eye_mark_size),
        ('Print Type', artwork.print_type),
        ('Barcode', artwork.barcode),
        ('Unwinding Direction', artwork.unwinding_direction),
        ('Packaging Supplier', artwork.packaging_supplier),
        ('Lamination', artwork.lamination),
    ]
    return [(label, str(value).strip()) for label, value in rows if _filled(value)]


def build_product_logo_check_rows(artwork):
    rows = [
        ('Logo Size', artwork.logo_size_status),
        ('Brand Text', artwork.brand_text_status),
        ('R Mark', artwork.r_mark_status),
        ('Number of Colors', artwork.number_of_colors),
    ]
    return [
        (label, str(value).strip())
        for label, value in rows
        if _filled(value)
    ]


def build_text_check_rows(artwork):
    rows = [
        ('Not Hydrogenated Text', artwork.not_hydrogenated_text),
        ('Net Weight "e"', artwork.net_weight_e),
        ('Pre-Printed Expiry / BB Date', artwork.pre_printed_expiry),
        ('Fortification Text', artwork.fortification_text),
        ('NEMA Requirements', artwork.nema_requirements),
        ('Triple Refined', artwork.triple_refined),
        ('Storage Condition', artwork.storage_condition),
    ]
    return [(label, str(value).strip()) for label, value in rows if _filled(value)]


def build_logo_check_entries(artwork):
    entries = []
    for check in artwork.logo_checks.all():
        if not _filled(check.status) and not _filled(check.colors_used):
            continue
        entries.append({
            'logo_name': check.logo_name,
            'status': check.status or '—',
            'colors_used': check.colors_used or '',
        })
    return entries


def build_color_spec_entries(artwork):
    entries = []
    for spec in artwork.color_specs.all().order_by('slot_number'):
        if not any(_filled(v) for v in (spec.color_name, spec.cmyk_values, spec.color_swatch)):
            continue
        entries.append(spec)
    return entries


def build_procurement_rows(artwork):
    rows = []
    if _filled(artwork.sap_material_description):
        rows.append(('SAP Material Description', artwork.sap_material_description.strip()))
    if _filled(artwork.sap_material_code):
        rows.append(('SAP Material Code', artwork.sap_material_code.strip()))
    if artwork.procurement_filled_by:
        rows.append((
            'Filled By',
            artwork.procurement_filled_by.get_full_name()
            or artwork.procurement_filled_by.username,
        ))
    if artwork.procurement_filled_date:
        rows.append(('Filled Date', artwork.procurement_filled_date.strftime('%d/%m/%Y')))
    return rows


def pair_rows(rows):
    """Pair label/value rows for a two-column table layout."""
    paired = []
    for index in range(0, len(rows), 2):
        left = rows[index]
        right = rows[index + 1] if index + 1 < len(rows) else None
        paired.append((left, right))
    return paired


def get_artwork_image_layout(primary_attachment):
    """
    Return layout hints for the dedicated artwork page.
    landscape when image is wider than tall.
    """
    if not primary_attachment or primary_attachment.file_type != 'artwork_image':
        return {'orientation': 'portrait', 'has_image': False}

    try:
        from PIL import Image
        with primary_attachment.file.open('rb') as handle:
            image = Image.open(handle)
            width, height = image.size
    except Exception:
        return {'orientation': 'portrait', 'has_image': True}

    return {
        'has_image': True,
        'orientation': 'landscape' if width > height else 'portrait',
        'width': width,
        'height': height,
    }
