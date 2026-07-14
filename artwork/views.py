import json
import logging
import mimetypes
import os
import shutil
import tempfile

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .config import (
    ARTWORK_STATUS_CONFIG, GROUP_STATUS_MAPPING, STAGE_ORDER,
    CHUNK_SIZE, MAX_UPLOAD_SIZE, DRAFT_STATUS, COMPLETED_STATUS,
)
from .color_utils import cmyk_to_hex
from .decorators import group_required, stage_approval_required
from .forms import (
    ArtworkRequestForm, LogoCheckFormSet, ColorSpecFormSet,
    StageApprovalForm, ProcurementForm, LogoTemplateForm, LogoTemplateCreateForm,
)
from .models import (
    ArtworkRequest, ArtworkAttachment, ArtworkLogoCheck,
    ArtworkColorSpec, LogoTemplate, ArtworkApprovalLog,
)
from .services import ArtworkStatusManager, ArtworkNotificationService
from .utils import (
    generate_artwork_number, validate_upload_file, detect_file_type,
    get_client_ip,
)
from .pdf_utils import (
    build_color_spec_entries,
    build_logo_check_entries,
    build_procurement_rows,
    build_product_detail_rows,
    build_product_logo_check_rows,
    build_text_check_rows,
    encode_image_srgb_b64,
    get_artwork_image_layout,
    pair_rows,
)
from .file_serving import stream_attachment

logger = logging.getLogger('artwork')

# Chunk upload temp directory
CHUNK_TEMP_DIR = os.path.join(tempfile.gettempdir(), 'artwork_chunks')


def _user_groups(user):
    return set(user.groups.values_list('name', flat=True))


def _can_view(artwork, user):
    if user.is_superuser:
        return True
    groups = _user_groups(user)
    if 'ADMIN' in groups:
        return True
    if artwork.created_by == user:
        return True
    for g in groups:
        if artwork.status in GROUP_STATUS_MAPPING.get(g, []):
            return True
    if artwork.status == COMPLETED_STATUS and 'PROCUREMENT' in groups:
        return True
    return False


def _can_edit(artwork, user):
    groups = _user_groups(user)
    if user.is_superuser or 'ADMIN' in groups:
        return True
    if 'DESIGN' in groups and artwork.created_by == user:
        return artwork.status in (DRAFT_STATUS, 'Design Created', 'Pending: Design Revision')
    return False


def _can_download_pdf(artwork, user):
    if artwork.status == COMPLETED_STATUS:
        return _can_view(artwork, user)
    groups = _user_groups(user)
    return user.is_superuser or 'ADMIN' in groups


def _artworks_for_user(user, queryset=None):
    queryset = queryset or ArtworkRequest.objects.all()
    groups = _user_groups(user)
    if user.is_superuser or 'ADMIN' in groups:
        return queryset
    visible_statuses = []
    for g in groups:
        visible_statuses.extend(GROUP_STATUS_MAPPING.get(g, []))
    if visible_statuses:
        return queryset.filter(Q(status__in=visible_statuses) | Q(created_by=user))
    return queryset.filter(created_by=user)


def _populate_logo_checks(artwork):
    templates = LogoTemplate.objects.filter(is_active=True)
    if not templates.exists():
        from .config import DEFAULT_LOGO_NAMES
        for i, name in enumerate(DEFAULT_LOGO_NAMES):
            LogoTemplate.objects.get_or_create(name=name, defaults={'display_order': i})
        templates = LogoTemplate.objects.filter(is_active=True)
    for tmpl in templates:
        ArtworkLogoCheck.objects.get_or_create(
            artwork_request=artwork,
            logo_name=tmpl.name,
            defaults={'logo_template': tmpl},
        )


def _populate_color_slots(artwork):
    for slot in range(1, 9):
        ArtworkColorSpec.objects.get_or_create(
            artwork_request=artwork,
            slot_number=slot,
        )


def _artwork_has_color_specs(artwork):
    return any(spec.has_content for spec in artwork.color_specs.all())


def _artwork_has_color_section(artwork):
    """True when the Color Specifications panel should show (colors and/or ingredients)."""
    if _artwork_has_color_specs(artwork):
        return True
    return bool((artwork.ingredients or '').strip())


def _build_color_slots_data(artwork=None, post_data=None):
    """Form row values for color slots; POST wins so validation errors keep user input."""
    db_by_slot = {}
    if artwork:
        for spec in artwork.color_specs.all():
            db_by_slot[spec.slot_number] = spec

    rows = []
    for slot in range(1, 9):
        if post_data is not None:
            name = (post_data.get(f'color_name_{slot}') or '').strip()
            cmyk = (post_data.get(f'color_cmyk_{slot}') or '').strip()
            hex_value = (post_data.get(f'color_hex_{slot}') or '').strip()
        else:
            spec = db_by_slot.get(slot)
            name = spec.color_name if spec else ''
            cmyk = spec.cmyk_values if spec else ''
            hex_value = spec.color_hex if spec else ''
        if not hex_value and cmyk:
            hex_value = cmyk_to_hex(cmyk)
        spec = db_by_slot.get(slot)
        swatch = spec.color_swatch if spec and spec.color_swatch else None
        rows.append({
            'slot': slot,
            'name': name,
            'cmyk': cmyk,
            'hex': hex_value,
            'swatch': swatch,
        })
    return rows


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    from django.conf import settings
    from users.ldap_client import ldap_is_available

    ldap_enabled = bool(getattr(settings, 'LDAP_ENABLED', False) and ldap_is_available())
    error = None
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        user = authenticate(request, username=username, password=password)
        if not user and username != username.lower():
            user = authenticate(request, username=username.lower(), password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        if ldap_enabled:
            error = (
                'Invalid username or password. Use your Kapa AD (Windows) credentials. '
                'If this persists, contact IT — LDAP may be unreachable from this machine.'
            )
        else:
            error = 'Invalid username or password.'
    return render(request, 'artwork/login.html', {
        'error': error,
        'ldap_enabled': ldap_enabled,
    })


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    groups = _user_groups(request.user)
    user = request.user
    base_qs = ArtworkRequest.objects.all()

    if not (user.is_superuser or 'ADMIN' in groups):
        visible_statuses = []
        for g in groups:
            visible_statuses.extend(GROUP_STATUS_MAPPING.get(g, []))
        if visible_statuses:
            base_qs = base_qs.filter(
                Q(status__in=visible_statuses) | Q(created_by=user)
            )

    pending_statuses = set()
    for g in groups:
        for status in GROUP_STATUS_MAPPING.get(g, []):
            if status.startswith('Pending:') and status != 'Pending: Design Revision':
                pending_statuses.add(status)

    if user.is_superuser or 'ADMIN' in groups:
        pending_statuses = set(
            ArtworkRequest.objects.filter(status__startswith='Pending:')
            .exclude(status='Pending: Design Revision')
            .values_list('status', flat=True)
            .distinct()
        )

    pending_count = ArtworkRequest.objects.filter(status__in=pending_statuses).count() if pending_statuses else 0

    recent_pending = ArtworkRequest.objects.filter(
        status__in=pending_statuses
    ).order_by('-date_created')[:5] if pending_statuses else []

    context = {
        'pending_count': pending_count,
        'completed_count': ArtworkRequest.objects.filter(
            status=COMPLETED_STATUS
        ).count(),
        'draft_count': ArtworkRequest.objects.filter(
            created_by=user, status=DRAFT_STATUS,
        ).count(),
        'my_count': ArtworkRequest.objects.filter(created_by=user).count(),
        'total_count': ArtworkRequest.objects.count(),
        'user_groups': groups,
        'recent_pending': recent_pending,
    }
    return render(request, 'artwork/dashboard.html', context)


def _ensure_logo_templates():
    templates = list(LogoTemplate.objects.filter(is_active=True))
    if not templates:
        from .config import DEFAULT_LOGO_NAMES
        for i, name in enumerate(DEFAULT_LOGO_NAMES):
            LogoTemplate.objects.get_or_create(name=name, defaults={'display_order': i})
        templates = list(LogoTemplate.objects.filter(is_active=True))
    return templates


def _get_logo_form_state(logo_templates, artwork=None, post_data=None):
    """Build per-template logo status/colors for the artwork form."""
    state = {tmpl.id: {'status': '', 'colors': ''} for tmpl in logo_templates}

    if post_data is not None:
        for tmpl in logo_templates:
            state[tmpl.id] = {
                'status': (post_data.get(f'logo_status_{tmpl.id}') or '').strip(),
                'colors': (post_data.get(f'logo_colors_{tmpl.id}') or '').strip(),
            }
        return state

    if artwork is not None:
        checks_by_template = {}
        checks_by_name = {}
        for check in artwork.logo_checks.all():
            if check.logo_template_id:
                checks_by_template[check.logo_template_id] = check
            checks_by_name[check.logo_name] = check
        for tmpl in logo_templates:
            check = checks_by_template.get(tmpl.id) or checks_by_name.get(tmpl.name)
            if check:
                state[tmpl.id] = {
                    'status': check.status or '',
                    'colors': check.colors_used or '',
                }
    return state


def _build_logo_tiles(logo_templates, artwork=None, post_data=None):
    state = _get_logo_form_state(logo_templates, artwork=artwork, post_data=post_data)
    return [
        {
            'template': tmpl,
            'status': state[tmpl.id]['status'],
            'colors': state[tmpl.id]['colors'],
        }
        for tmpl in logo_templates
    ]


def _save_logo_checks_from_post(artwork, post_data):
    templates = _ensure_logo_templates()
    for tmpl in templates:
        status = (post_data.get(f'logo_status_{tmpl.id}') or '').strip()
        colors = (post_data.get(f'logo_colors_{tmpl.id}') or '').strip()
        check, _ = ArtworkLogoCheck.objects.get_or_create(
            artwork_request=artwork,
            logo_name=tmpl.name,
            defaults={'logo_template': tmpl},
        )
        check.logo_template = tmpl
        check.status = status
        check.colors_used = colors
        check.save()


def _save_color_specs_from_post(artwork, post_data, files):
    _populate_color_slots(artwork)
    for spec in artwork.color_specs.all():
        slot = spec.slot_number
        if f'color_name_{slot}' in post_data:
            spec.color_name = (post_data.get(f'color_name_{slot}') or '').strip()
        if f'color_cmyk_{slot}' in post_data:
            spec.cmyk_values = (post_data.get(f'color_cmyk_{slot}') or '').strip()
        hex_value = (post_data.get(f'color_hex_{slot}') or '').strip()
        spec.color_hex = hex_value or cmyk_to_hex(spec.cmyk_values)
        swatch = files.get(f'color_swatch_{slot}')
        if swatch:
            spec.color_swatch = swatch
        spec.save()


def _save_artwork_files(artwork, request):
    """Save main artwork files from a standard multipart upload."""
    files = request.FILES.getlist('artwork_files')
    if not files:
        return []
    errors = []
    has_primary = artwork.attachments.filter(is_primary=True).exists()
    for i, uploaded in enumerate(files):
        file_errors = validate_upload_file(uploaded)
        if file_errors:
            errors.extend(file_errors)
            continue
        is_primary = (i == 0 and not has_primary)
        ArtworkAttachment.objects.create(
            artwork_request=artwork,
            file=uploaded,
            original_filename=uploaded.name,
            file_type=detect_file_type(uploaded.name),
            uploaded_by=request.user,
            is_primary=is_primary,
            file_size=uploaded.size,
            mime_type=getattr(uploaded, 'content_type', '') or '',
        )
        if is_primary:
            has_primary = True
    return errors


@login_required
@group_required('DESIGN', 'ADMIN')
def artwork_create(request):
    logo_templates = _ensure_logo_templates()

    if request.method == 'POST':
        form = ArtworkRequestForm(request.POST, request.FILES)
        form.is_submitting = request.POST.get('action') == 'submit'
        if form.is_valid():
            artwork = form.save(commit=False)
            artwork.artwork_no = generate_artwork_number()
            artwork.created_by = request.user
            artwork.current_user = request.user
            artwork.status = DRAFT_STATUS
            artwork.save()
            _save_logo_checks_from_post(artwork, request.POST)
            _save_color_specs_from_post(artwork, request.POST, request.FILES)
            upload_errors = _save_artwork_files(artwork, request)
            if upload_errors:
                messages.warning(request, 'Some files were skipped: ' + '; '.join(upload_errors))
            action = request.POST.get('action', 'save')
            if action == 'submit':
                ArtworkStatusManager.reset_approval_flags(artwork)
                ArtworkStatusManager.submit_for_approval(
                    artwork, request.user, ip=get_client_ip(request)
                )
                messages.success(request, f'Artwork {artwork.artwork_no} submitted for approval.')
                return redirect('artwork-detail', artwork_no=artwork.artwork_no)
            messages.success(request, f'Draft {artwork.artwork_no} saved. You can continue editing later.')
            return redirect('artwork-edit', artwork_no=artwork.artwork_no)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ArtworkRequestForm()

    post_data = request.POST if request.method == 'POST' else None
    return render(request, 'artwork/create.html', {
        'form': form,
        'logo_templates': logo_templates,
        'logo_tiles': _build_logo_tiles(logo_templates, post_data=post_data),
        'color_slots_data': _build_color_slots_data(post_data=post_data),
        'is_edit': False,
        'artwork': None,
        'attachments': [],
    })


@login_required
def artwork_edit(request, artwork_no):
    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    if not _can_edit(artwork, request.user):
        raise PermissionDenied

    if not artwork.logo_checks.exists():
        _populate_logo_checks(artwork)
    if not artwork.color_specs.exists():
        _populate_color_slots(artwork)

    if request.method == 'POST':
        form = ArtworkRequestForm(request.POST, request.FILES, instance=artwork)
        form.is_submitting = request.POST.get('action') == 'submit'
        if form.is_valid():
            previous_status = artwork.status
            artwork = form.save(commit=False)
            action = request.POST.get('action', 'save')
            if action != 'submit' and artwork.status in (DRAFT_STATUS, 'Design Created'):
                artwork.status = DRAFT_STATUS
            artwork.save()
            _save_logo_checks_from_post(artwork, request.POST)
            _save_color_specs_from_post(artwork, request.POST, request.FILES)
            upload_errors = _save_artwork_files(artwork, request)
            if upload_errors:
                messages.warning(request, 'Some files were skipped: ' + '; '.join(upload_errors))
            if action == 'submit':
                ArtworkStatusManager.reset_approval_flags(artwork)
                ArtworkStatusManager.submit_for_approval(
                    artwork, request.user, ip=get_client_ip(request)
                )
                if previous_status == 'Pending: Design Revision':
                    ArtworkStatusManager.log_action(
                        artwork, request.user, 'resubmitted', 'marketing',
                        status_before=previous_status,
                        status_after=artwork.status,
                        ip=get_client_ip(request),
                    )
                messages.success(request, 'Artwork submitted for approval.')
                return redirect('artwork-detail', artwork_no=artwork.artwork_no)
            messages.success(request, 'Draft saved.')
            return redirect('artwork-edit', artwork_no=artwork.artwork_no)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ArtworkRequestForm(instance=artwork)

    logo_templates = _ensure_logo_templates()
    post_data = request.POST if request.method == 'POST' else None
    return render(request, 'artwork/create.html', {
        'form': form,
        'logo_templates': logo_templates,
        'logo_tiles': _build_logo_tiles(logo_templates, artwork=artwork, post_data=post_data),
        'color_slots_data': _build_color_slots_data(artwork=artwork, post_data=post_data),
        'is_edit': True,
        'artwork': artwork,
        'attachments': artwork.attachments.all(),
    })


@login_required
@require_GET
def logo_template_icon(request, pk):
    """Serve reusable logo template icons (works with private media / S3)."""
    tmpl = get_object_or_404(LogoTemplate, pk=pk)
    if not tmpl.is_active:
        groups = _user_groups(request.user)
        if not (request.user.is_superuser or groups.intersection({'DESIGN', 'ADMIN'})):
            raise Http404('Logo not available')
    if not tmpl.icon:
        raise Http404('Logo icon not uploaded')
    filename = tmpl.icon.name.split('/')[-1]
    content_type = mimetypes.guess_type(filename)[0] or 'image/png'
    file_handle = tmpl.icon.open('rb')
    response = FileResponse(file_handle, content_type=content_type)
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    response['Cache-Control'] = 'private, max-age=3600'
    return response


@login_required
@group_required('DESIGN', 'ADMIN')
def logo_library(request):
    """Designers manage reusable logo images for artwork forms."""
    logos = LogoTemplate.objects.all().order_by('display_order', 'name')

    if request.method == 'POST':
        form = LogoTemplateCreateForm(request.POST, request.FILES, require_icon=True)
        if form.is_valid():
            logo = form.save(commit=False)
            last = LogoTemplate.objects.order_by('-display_order').first()
            logo.display_order = (last.display_order + 1) if last else 0
            logo.save()
            messages.success(request, f'Logo "{logo.name}" saved. It is now available on the artwork form.')
            return redirect('logo-library')
        messages.error(request, 'Could not save logo. Check the form below.')
    else:
        form = LogoTemplateCreateForm(require_icon=True)

    return render(request, 'artwork/logo_library.html', {
        'form': form,
        'logos': logos,
    })


@login_required
@group_required('DESIGN', 'ADMIN')
def logo_library_edit(request, pk):
    logo = get_object_or_404(LogoTemplate, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        if action == 'delete':
            name = logo.name
            logo.delete()
            messages.success(request, f'Logo "{name}" removed from the library.')
            return redirect('logo-library')

        form = LogoTemplateForm(
            request.POST, request.FILES, instance=logo, require_icon=False,
        )
        if form.is_valid():
            form.save()
            messages.success(request, f'Logo "{logo.name}" updated.')
            return redirect('logo-library')
        messages.error(request, 'Could not update logo.')
    else:
        form = LogoTemplateForm(instance=logo, require_icon=False)

    return render(request, 'artwork/logo_library_edit.html', {
        'form': form,
        'logo': logo,
    })


@login_required
@group_required('DESIGN', 'ADMIN')
@require_POST
def logo_library_toggle(request, pk):
    logo = get_object_or_404(LogoTemplate, pk=pk)
    logo.is_active = not logo.is_active
    logo.save(update_fields=['is_active'])
    state = 'shown' if logo.is_active else 'hidden'
    messages.success(request, f'Logo "{logo.name}" is now {state} on the artwork form.')
    return redirect('logo-library')


@login_required
def artwork_detail(request, artwork_no):
    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    if not _can_view(artwork, request.user):
        raise PermissionDenied
    return render(request, 'artwork/detail.html', {
        'artwork': artwork,
        'approval_timeline': _build_approval_timeline(artwork),
        'attachments': artwork.attachments.all(),
        'has_color_specs': _artwork_has_color_specs(artwork),
        'has_color_section': _artwork_has_color_section(artwork),
    })


def _build_approval_timeline(artwork):
    timeline = []
    timeline.append({
        'stage': 'Design',
        'name': artwork.created_by.get_full_name() or artwork.created_by.username,
        'status': 'Submitted',
        'date': artwork.date_created,
        'comments': artwork.reason_for_update,
    })
    for stage_key in STAGE_ORDER:
        cfg = ARTWORK_STATUS_CONFIG[stage_key]
        prefix = cfg['field_prefix']
        approved = getattr(artwork, f'{prefix}_approved', False)
        rejected = getattr(artwork, f'{prefix}_rejected', False)
        approver = getattr(artwork, f'{prefix}_by', None)
        if approved:
            status = 'Approved'
            date = getattr(artwork, f'{prefix}_date_approved', None)
        elif rejected:
            status = 'Rejected'
            date = getattr(artwork, f'{prefix}_date_rejected', None)
        else:
            status = 'Pending'
            date = None
        timeline.append({
            'stage': cfg['display'],
            'name': approver.get_full_name() if approver else '—',
            'status': status,
            'date': date,
            'comments': getattr(artwork, f'{prefix}_comments', ''),
        })
    return timeline


@login_required
def artwork_all(request):
    artworks = _artworks_for_user(request.user).select_related('created_by')
    search = request.GET.get('q', '')
    if search:
        artworks = artworks.filter(
            Q(artwork_no__icontains=search) |
            Q(product_name__icontains=search) |
            Q(sku_size__icontains=search)
        )
    status_filter = request.GET.get('status', '')
    if status_filter:
        artworks = artworks.filter(status=status_filter)
    return render(request, 'artwork/all.html', {
        'artworks': artworks,
        'search': search,
        'status_filter': status_filter,
        'statuses': ArtworkRequest.objects.values_list('status', flat=True).distinct(),
        'page_title': 'All Artworks',
        'active_tab': 'all',
        'show_pdf': True,
    })


@login_required
def artwork_my(request):
    artworks = ArtworkRequest.objects.filter(
        created_by=request.user,
    ).select_related('created_by').order_by('-date_created')
    return render(request, 'artwork/all.html', {
        'artworks': artworks,
        'page_title': 'My Artworks',
        'active_tab': 'my',
        'show_pdf': True,
    })


@login_required
def artwork_drafts(request):
    groups = _user_groups(request.user)
    if request.user.is_superuser or 'ADMIN' in groups:
        artworks = ArtworkRequest.objects.filter(status=DRAFT_STATUS)
    else:
        artworks = ArtworkRequest.objects.filter(
            created_by=request.user, status=DRAFT_STATUS,
        )
    artworks = artworks.select_related('created_by').order_by('-date_created')
    return render(request, 'artwork/all.html', {
        'artworks': artworks,
        'page_title': 'Drafts',
        'active_tab': 'drafts',
        'show_pdf': False,
    })


@login_required
def artwork_pending(request):
    groups = _user_groups(request.user)
    statuses = []
    for g in groups:
        statuses.extend(GROUP_STATUS_MAPPING.get(g, []))
    if request.user.is_superuser or 'ADMIN' in groups:
        statuses = list(
            ArtworkRequest.objects.filter(status__startswith='Pending:')
            .values_list('status', flat=True)
            .distinct()
        )
    artworks = ArtworkRequest.objects.filter(
        status__in=statuses,
    ).select_related('created_by').order_by('-date_created')
    search = request.GET.get('q', '')
    if search:
        artworks = artworks.filter(
            Q(artwork_no__icontains=search) |
            Q(product_name__icontains=search) |
            Q(sku_size__icontains=search)
        )
    return render(request, 'artwork/all.html', {
        'artworks': artworks,
        'search': search,
        'page_title': 'Pending',
        'active_tab': 'pending',
        'show_pdf': False,
        'show_search': True,
    })


@login_required
def artwork_completed(request):
    artworks = _artworks_for_user(
        request.user,
        ArtworkRequest.objects.filter(status=COMPLETED_STATUS),
    ).select_related('created_by').order_by('-date_created')
    search = request.GET.get('q', '')
    if search:
        artworks = artworks.filter(
            Q(artwork_no__icontains=search) |
            Q(product_name__icontains=search) |
            Q(sku_size__icontains=search)
        )
    return render(request, 'artwork/all.html', {
        'artworks': artworks,
        'search': search,
        'page_title': 'Completed',
        'active_tab': 'completed',
        'show_pdf': True,
        'pdf_primary': True,
        'show_search': True,
    })


def _approval_view(request, artwork_no, stage_key, template_name):
    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    cfg = ARTWORK_STATUS_CONFIG[stage_key]
    if artwork.status != cfg['db_status']:
        messages.warning(request, 'This artwork is not at your approval stage.')
        return redirect('artwork-detail', artwork_no=artwork_no)

    prefix = cfg['field_prefix']
    already_acted = getattr(artwork, f'{prefix}_approved') or getattr(artwork, f'{prefix}_rejected')

    if request.method == 'POST':
        form = StageApprovalForm(request.POST)
        action = request.POST.get('action')
        if form.is_valid() and action in ('approved', 'rejected'):
            comments = form.cleaned_data['comments']
            ip = get_client_ip(request)
            if action == 'approved':
                ArtworkStatusManager.approve(artwork, stage_key, request.user, comments, ip)
                return JsonResponse({'success': True, 'message': 'Approved successfully.', 'redirect': '/artwork/pending/'})
            else:
                ArtworkStatusManager.reject(artwork, stage_key, request.user, comments, ip)
                return JsonResponse({'success': True, 'message': 'Rejected. Sent back to Design.', 'redirect': '/artwork/pending/'})
        return JsonResponse({'success': False, 'message': 'Invalid form data.'}, status=400)

    form = StageApprovalForm()
    if not artwork.logo_checks.exists():
        _populate_logo_checks(artwork)
    if not artwork.color_specs.exists():
        _populate_color_slots(artwork)
    logo_templates = _ensure_logo_templates()
    logo_tiles = _build_logo_tiles(logo_templates, artwork=artwork)
    okay_count = artwork.logo_checks.filter(status='Okay').count()
    na_count = artwork.logo_checks.filter(status='N/A').count()
    logo_summary_parts = []
    if okay_count:
        logo_summary_parts.append(f'{okay_count} selected')
    if na_count:
        logo_summary_parts.append(f'{na_count} N/A')
    logo_summary = ', '.join(logo_summary_parts) if logo_summary_parts else 'None marked'

    return render(request, template_name, {
        'artwork': artwork,
        'form': form,
        'stage_key': stage_key,
        'stage_config': cfg,
        'already_acted': already_acted,
        'approval_timeline': _build_approval_timeline(artwork),
        'attachments': artwork.attachments.all(),
        'primary_attachment': artwork.primary_attachment,
        'logo_tiles': logo_tiles,
        'logo_summary': logo_summary,
        'has_color_specs': _artwork_has_color_specs(artwork),
        'has_color_section': _artwork_has_color_section(artwork),
    })


@stage_approval_required('marketing')
def marketing_approval(request, artwork_no):
    return _approval_view(request, artwork_no, 'marketing', 'artwork/approval.html')


@stage_approval_required('qa')
def qa_approval(request, artwork_no):
    return _approval_view(request, artwork_no, 'qa', 'artwork/approval.html')


@stage_approval_required('operations_hod')
def operations_approval(request, artwork_no):
    return _approval_view(request, artwork_no, 'operations_hod', 'artwork/approval.html')


@stage_approval_required('product_dev')
def product_dev_approval(request, artwork_no):
    return _approval_view(request, artwork_no, 'product_dev', 'artwork/approval.html')


@stage_approval_required('milan')
def milan_approval(request, artwork_no):
    return _approval_view(request, artwork_no, 'milan', 'artwork/approval.html')


@login_required
@group_required('PROCUREMENT', 'ADMIN')
def procurement_view(request, artwork_no):
    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    if artwork.status != 'Completed / Approved':
        messages.warning(request, 'Procurement can only be filled after full approval.')
        return redirect('artwork-detail', artwork_no=artwork_no)
    if request.method == 'POST':
        form = ProcurementForm(request.POST, instance=artwork)
        if form.is_valid():
            artwork = form.save(commit=False)
            artwork.procurement_filled_by = request.user
            artwork.procurement_filled_date = timezone.now()
            artwork.save()
            messages.success(request, 'SAP details saved.')
            return redirect('artwork-detail', artwork_no=artwork_no)
    else:
        form = ProcurementForm(instance=artwork)
    return render(request, 'artwork/procurement.html', {'artwork': artwork, 'form': form})


# --- File handling ---

@login_required
@require_POST
def upload_chunk(request, artwork_no):
    """Chunked file upload to prevent browser hang on large files."""
    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    if not _can_edit(artwork, request.user) and not request.user.is_superuser:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    chunk = request.FILES.get('chunk')
    chunk_index = int(request.POST.get('chunk_index', 0))
    total_chunks = int(request.POST.get('total_chunks', 1))
    upload_id = request.POST.get('upload_id', '')
    filename = request.POST.get('filename', 'upload')
    description = request.POST.get('description', '')
    is_primary = request.POST.get('is_primary', 'false') == 'true'

    os.makedirs(CHUNK_TEMP_DIR, exist_ok=True)
    chunk_path = os.path.join(CHUNK_TEMP_DIR, f'{upload_id}_{chunk_index}')

    with open(chunk_path, 'wb') as f:
        for data in chunk.chunks(CHUNK_SIZE):
            f.write(data)

    if chunk_index == total_chunks - 1:
        final_path = os.path.join(CHUNK_TEMP_DIR, f'{upload_id}_final')
        with open(final_path, 'wb') as outfile:
            for i in range(total_chunks):
                cp = os.path.join(CHUNK_TEMP_DIR, f'{upload_id}_{i}')
                with open(cp, 'rb') as infile:
                    shutil.copyfileobj(infile, outfile)
                os.remove(cp)

        file_size = os.path.getsize(final_path)
        if file_size > MAX_UPLOAD_SIZE:
            os.remove(final_path)
            return JsonResponse({'error': 'File too large'}, status=400)

        from django.core.files import File
        with open(final_path, 'rb') as f:
            attachment = ArtworkAttachment(
                artwork_request=artwork,
                original_filename=filename,
                file_type=detect_file_type(filename),
                description=description,
                uploaded_by=request.user,
                is_primary=is_primary,
                file_size=file_size,
            )
            attachment.file.save(filename, File(f), save=True)
        os.remove(final_path)
        return JsonResponse({
            'success': True,
            'attachment_id': attachment.id,
            'filename': attachment.original_filename,
            'is_primary': attachment.is_primary,
        })

    return JsonResponse({'success': True, 'chunk_received': chunk_index})


@login_required
def attachment_list(request, artwork_no):
    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    if not _can_view(artwork, request.user):
        raise PermissionDenied
    return JsonResponse({
        'attachments': [
            {
                'id': a.id,
                'filename': a.original_filename,
                'file_type': a.file_type,
                'description': a.description,
                'is_primary': a.is_primary,
                'url': reverse('attachment-download', kwargs={'artwork_no': artwork_no, 'file_id': a.id}),
                'preview_url': reverse('attachment-preview', kwargs={'artwork_no': artwork_no, 'file_id': a.id}),
            }
            for a in artwork.attachments.all()
        ]
    })


@login_required
def attachment_download(request, artwork_no, file_id):
    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    if not _can_view(artwork, request.user):
        raise PermissionDenied
    attachment = get_object_or_404(ArtworkAttachment, id=file_id, artwork_request=artwork)
    return stream_attachment(attachment, as_attachment=True)


@login_required
def attachment_preview(request, artwork_no, file_id):
    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    if not _can_view(artwork, request.user):
        raise PermissionDenied
    attachment = get_object_or_404(ArtworkAttachment, id=file_id, artwork_request=artwork)
    return stream_attachment(attachment, as_attachment=False)


@login_required
@require_POST
def set_primary_attachment(request, artwork_no, file_id):
    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    if not _can_edit(artwork, request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    attachment = get_object_or_404(ArtworkAttachment, id=file_id, artwork_request=artwork)
    attachment.is_primary = True
    attachment.save()
    return JsonResponse({'success': True})


@login_required
@require_POST
def delete_attachment(request, artwork_no, file_id):
    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    if not _can_edit(artwork, request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    attachment = get_object_or_404(ArtworkAttachment, id=file_id, artwork_request=artwork)
    attachment.file.delete(save=False)
    attachment.delete()
    return JsonResponse({'success': True})


# --- API ---

@login_required
@require_GET
def api_artwork_details(request, artwork_no):
    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    if not _can_view(artwork, request.user):
        raise PermissionDenied
    data = {
        'artwork_no': artwork.artwork_no,
        'product_name': artwork.product_name,
        'sku_size': artwork.sku_size,
        'status': artwork.status,
        'reason_for_update': artwork.reason_for_update,
        'revision_count': artwork.revision_count,
        'created_by': artwork.created_by.username,
        'date_created': artwork.date_created.isoformat(),
    }
    return JsonResponse(data)


@login_required
@require_GET
def api_artwork_comments(request, artwork_no):
    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    if not _can_view(artwork, request.user):
        raise PermissionDenied
    logs = artwork.approval_logs.all()
    return JsonResponse({
        'comments': [
            {
                'user': log.user.username if log.user else 'System',
                'action': log.action,
                'stage': log.stage,
                'comments': log.comments,
                'timestamp': log.timestamp.isoformat(),
            }
            for log in logs
        ]
    })


@login_required
@require_GET
def api_generate_artwork_number(request):
    return JsonResponse({'artwork_no': generate_artwork_number()})


# --- PDF ---

@login_required
def download_artwork_pdf(request, artwork_no):
    import base64
    import pdfkit
    from django.conf import settings

    artwork = get_object_or_404(ArtworkRequest, artwork_no=artwork_no)
    if not _can_download_pdf(artwork, request.user):
        raise PermissionDenied
    logo_b64 = ''
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'kapa_logo.png')
    letterhead_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'Letterhead.png')
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode()
    elif os.path.exists(letterhead_path):
        with open(letterhead_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode()

    primary = artwork.primary_attachment
    primary_b64 = ''
    primary_mime = 'image/jpeg'
    if primary and primary.file_type == 'artwork_image':
        b64, mime = encode_image_srgb_b64(primary.file)
        if b64:
            primary_b64 = b64
            primary_mime = mime or primary.mime_type or 'image/jpeg'

    color_specs_data = []
    for spec in build_color_spec_entries(artwork):
        swatch_b64 = ''
        swatch_mime = 'image/jpeg'
        if spec.color_swatch:
            swatch_b64, swatch_mime = encode_image_srgb_b64(spec.color_swatch)
        color_specs_data.append({
            'slot_number': spec.slot_number,
            'color_name': spec.color_name or '',
            'cmyk_values': spec.cmyk_values or '',
            'swatch_b64': swatch_b64,
            'swatch_mime': swatch_mime or 'image/jpeg',
            'hex': spec.swatch_color,
        })

    product_detail_rows = build_product_detail_rows(artwork)
    product_logo_rows = build_product_logo_check_rows(artwork)
    text_check_rows = build_text_check_rows(artwork)
    procurement_rows = build_procurement_rows(artwork)
    artwork_layout = get_artwork_image_layout(primary)

    html = render(request, 'artwork/pdf/artwork_report_pdf.html', {
        'artwork': artwork,
        'logo_b64': logo_b64,
        'primary_b64': primary_b64,
        'primary_mime': primary_mime,
        'approval_timeline': _build_approval_timeline(artwork),
        'logo_check_entries': build_logo_check_entries(artwork),
        'color_specs_data': color_specs_data,
        'product_detail_rows': product_detail_rows,
        'product_detail_pairs': pair_rows(product_detail_rows),
        'product_logo_rows': product_logo_rows,
        'text_check_rows': text_check_rows,
        'text_check_pairs': pair_rows(text_check_rows),
        'procurement_rows': procurement_rows,
        'procurement_pairs': pair_rows(procurement_rows),
        'artwork_layout': artwork_layout,
        'is_approved': artwork.status == COMPLETED_STATUS,
        'completed_date': artwork.milan_date_approved or artwork.last_status_change,
    }).content.decode()

    options = {
        'page-size': 'A4',
        'margin-top': '8mm',
        'margin-right': '8mm',
        'margin-bottom': '8mm',
        'margin-left': '8mm',
        'encoding': 'UTF-8',
        'enable-local-file-access': None,
        'dpi': 300,
        'image-quality': 95,
        'print-media-type': None,
    }
    config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_PATH)
    pdf = pdfkit.from_string(html, False, options=options, configuration=config)
    response = HttpResponse(pdf, content_type='application/pdf')
    disposition = 'inline' if request.GET.get('inline') else 'attachment'
    response['Content-Disposition'] = f'{disposition}; filename="{artwork.artwork_no}_approval.pdf"'
    return response
