"""Active Directory user sync — shared by management command and admin UI."""
import logging
import re
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from users.models import Profile

logger = logging.getLogger('users')

try:
    import ldap  # type: ignore
except Exception:
    ldap = None


@dataclass
class LDAPSyncResult:
    success: bool = False
    message: str = ''
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    total_ldap_entries: int = 0
    log_lines: list = field(default_factory=list)

    def as_dict(self):
        return {
            'success': self.success,
            'message': self.message,
            'created': self.created,
            'updated': self.updated,
            'skipped': self.skipped,
            'errors': self.errors,
            'total_ldap_entries': self.total_ldap_entries,
        }


def run_ldap_sync(
    *,
    dry_run=False,
    update_existing=True,
    limit=None,
    verbose=False,
    triggered_by=None,
    log_model=None,
):
    """Sync AD users into Django User + Profile. Returns LDAPSyncResult."""
    result = LDAPSyncResult()

    if ldap is None:
        result.message = 'python-ldap is not installed on this server.'
        _persist_log(log_model, triggered_by, dry_run, update_existing, result)
        return result

    if not settings.LDAP_BIND_DN or not settings.LDAP_PASSWORD:
        result.message = 'LDAP_BIND_DN and LDAP_PASSWORD must be configured in environment.'
        _persist_log(log_model, triggered_by, dry_run, update_existing, result)
        return result

    User = get_user_model()
    conn = ldap.initialize(settings.LDAP_SERVER_URI)
    conn.set_option(ldap.OPT_REFERRALS, 0)
    conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 30)

    try:
        conn.simple_bind_s(settings.LDAP_BIND_DN, settings.LDAP_PASSWORD)
    except ldap.INVALID_CREDENTIALS:
        result.message = 'Invalid LDAP service account credentials.'
        _persist_log(log_model, triggered_by, dry_run, update_existing, result)
        return result
    except ldap.SERVER_DOWN:
        result.message = f'LDAP server unreachable at {settings.LDAP_SERVER_URI}.'
        _persist_log(log_model, triggered_by, dry_run, update_existing, result)
        return result
    except Exception as exc:
        result.message = f'LDAP connection failed: {exc}'
        _persist_log(log_model, triggered_by, dry_run, update_existing, result)
        return result

    search_filter = '(&(objectClass=user)(objectCategory=person)(sAMAccountName=*))'
    attrs = [
        'sAMAccountName', 'mail', 'givenName', 'sn', 'title',
        'displayName', 'telephoneNumber',
    ]

    try:
        results = conn.search_s(
            settings.LDAP_BASE_DN, ldap.SCOPE_SUBTREE, search_filter, attrs
        )
        result.total_ldap_entries = len(results)
    except Exception as exc:
        conn.unbind_s()
        result.message = f'LDAP search failed: {exc}'
        _persist_log(log_model, triggered_by, dry_run, update_existing, result)
        return result

    processed = 0
    for dn, entry_attrs in results:
        if not entry_attrs:
            result.skipped += 1
            continue

        username = _decode(entry_attrs, 'sAMAccountName')
        if not username or _is_service_account(username):
            result.skipped += 1
            continue

        username = username.lower()
        email = _decode(entry_attrs, 'mail') or f'{username}@kapa-oil.local'
        first_name = _decode(entry_attrs, 'givenName')
        last_name = _decode(entry_attrs, 'sn')
        position = _decode(entry_attrs, 'title')
        display_name = _decode(entry_attrs, 'displayName')
        phone = _decode(entry_attrs, 'telephoneNumber')
        ou_name = _extract_ou_from_dn(dn)

        if not first_name and display_name:
            parts = display_name.split()
            first_name = parts[0]
            last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''
        if not first_name:
            first_name = username

        dept_name = ''
        if ou_name:
            dept_config = getattr(settings, 'OU_TO_DEPARTMENT_MAP', {}).get(ou_name)
            dept_name = dept_config['name'] if dept_config else ou_name

        if verbose:
            result.log_lines.append(f'{username} | {email} | {dept_name or "—"}')

        if dry_run:
            result.updated += 1
            processed += 1
            if limit and processed >= limit:
                break
            continue

        try:
            with transaction.atomic():
                existing = User.objects.filter(
                    Q(username__iexact=username) | Q(profile__ldap_dn=dn)
                ).select_related('profile').first()

                if existing and not update_existing:
                    result.skipped += 1
                    processed += 1
                    if limit and processed >= limit:
                        break
                    continue

                if existing:
                    user = existing
                    user.username = username
                    user.email = email
                    user.first_name = first_name
                    user.last_name = last_name or ''
                    user.is_active = True
                    user.set_unusable_password()
                    user.save()
                    created = False
                else:
                    user = User(
                        username=username,
                        email=email,
                        first_name=first_name,
                        last_name=last_name or '',
                        is_active=True,
                    )
                    user.set_unusable_password()
                    user.save()
                    created = True

                profile, _ = Profile.objects.get_or_create(user=user)
                profile.email = email
                profile.ldap_dn = dn
                profile.position = position
                profile.extension_no = phone
                profile.department = dept_name
                profile.is_active = True
                profile.save()

                if created:
                    result.created += 1
                else:
                    result.updated += 1

                processed += 1
                if limit and processed >= limit:
                    break

        except Exception as exc:
            result.errors += 1
            result.log_lines.append(f'ERROR {username}: {exc}')
            logger.exception('LDAP sync error for %s', username)

    conn.unbind_s()
    result.success = result.errors == 0
    prefix = '[DRY RUN] ' if dry_run else ''
    result.message = (
        f"{prefix}Sync complete — created {result.created}, "
        f"updated {result.updated}, skipped {result.skipped}, errors {result.errors}"
    )
    _persist_log(log_model, triggered_by, dry_run, update_existing, result)
    return result


def _persist_log(log_model, triggered_by, dry_run, update_existing, result):
    if log_model is None:
        return
    from users.models import LDAPSyncLog
    LDAPSyncLog.objects.create(
        triggered_by=triggered_by,
        dry_run=dry_run,
        update_existing=update_existing,
        created_count=result.created,
        updated_count=result.updated,
        skipped_count=result.skipped,
        errors_count=result.errors,
        total_ldap_entries=result.total_ldap_entries,
        success=result.success,
        message=result.message,
        completed_at=timezone.now(),
    )


def _decode(attrs, key):
    for attr_key in (key, key.encode()):
        if attr_key in attrs and attrs[attr_key]:
            val = attrs[attr_key][0]
            if isinstance(val, bytes):
                return val.decode('utf-8', errors='ignore').strip()
            return str(val).strip()
    return ''


def _extract_ou_from_dn(dn):
    match = re.search(r'OU=([^,]+)', dn, re.IGNORECASE)
    return match.group(1) if match else None


def _is_service_account(username):
    username_lower = username.lower()
    if username_lower in {'administrator', 'guest', 'krbtgt', 'admin'}:
        return True
    if username_lower.endswith('$') or username_lower.startswith('sm_'):
        return True
    for keyword in ('healthmailbox', 'extest', 'systemmail', 'discoveryse', 'federationm'):
        if keyword in username_lower:
            return True
    return False
