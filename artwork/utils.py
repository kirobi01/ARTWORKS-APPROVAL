import mimetypes
import os
import re

from django.utils import timezone

from .config import ALLOWED_MIME_TYPES, ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_SIZE
from .models import ArtworkRequest


def generate_artwork_number():
    """Generate ART-YYYY-NNNN format, e.g. ART-2025-0001."""
    current_year = timezone.now().year
    pattern = re.compile(rf'^ART-{current_year}-(\d{{4}})$', re.IGNORECASE)
    last_entry = (
        ArtworkRequest.objects.filter(artwork_no__iregex=rf'^ART-{current_year}-\d{{4}}$')
        .order_by('-artwork_no')
        .first()
    )
    if last_entry:
        match = pattern.match(last_entry.artwork_no)
        new_number = int(match.group(1)) + 1 if match else 1
    else:
        new_number = 1
    return f'ART-{current_year}-{str(new_number).zfill(4)}'


ARTWORK_NO_RE = re.compile(r'^ART-\d{4}-\d{4}$', re.IGNORECASE)


def allocate_artwork_number(preferred=None):
    """
    Return a free artwork number.

    Uses ``preferred`` when it matches ART-YYYY-NNNN and is not already taken
    (so the create page can keep the number shown to the designer).
    """
    preferred = (preferred or '').strip().upper()
    if preferred and ARTWORK_NO_RE.fullmatch(preferred):
        if not ArtworkRequest.objects.filter(artwork_no__iexact=preferred).exists():
            return preferred
    for _ in range(12):
        candidate = generate_artwork_number()
        if not ArtworkRequest.objects.filter(artwork_no__iexact=candidate).exists():
            return candidate
    # Extremely unlikely fallback if many concurrent creates collide
    stamp = timezone.now().strftime('%H%M%S')
    return f'ART-{timezone.now().year}-{stamp[:4]}'


def validate_upload_file(uploaded_file):
    """Validate file extension, MIME type, and size."""
    errors = []
    name = uploaded_file.name
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        errors.append(f'File type {ext} is not allowed.')
    if uploaded_file.size > MAX_UPLOAD_SIZE:
        errors.append(f'File exceeds maximum size of {MAX_UPLOAD_SIZE // (1024*1024)}MB.')
    content_type = getattr(uploaded_file, 'content_type', '') or mimetypes.guess_type(name)[0] or ''
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        # Allow if extension is valid (some browsers send generic MIME)
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            errors.append(f'MIME type {content_type} is not allowed.')
    return errors


def detect_file_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext == '.pdf':
        return 'pdf'
    if ext in {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.svg'}:
        return 'artwork_image'
    return 'reference'


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def get_user_email(user):
    if not user:
        return None
    if hasattr(user, 'profile') and user.profile.email:
        return user.profile.email
    return user.email or None
