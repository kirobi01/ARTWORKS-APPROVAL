"""LDAP helpers — uses ldap3 (Windows-friendly) with optional python-ldap fallback."""
import logging

from django.conf import settings

logger = logging.getLogger('users')

try:
    import ldap3
    from ldap3 import NTLM
    from ldap3.core.exceptions import LDAPBindError, LDAPException, LDAPSocketOpenError
    LDAP3_AVAILABLE = True
except ImportError:
    ldap3 = None
    NTLM = None
    LDAP3_AVAILABLE = False

try:
    import ldap as python_ldap  # type: ignore
    PYTHON_LDAP_AVAILABLE = True
except ImportError:
    python_ldap = None
    PYTHON_LDAP_AVAILABLE = False


def ldap_is_available():
    return LDAP3_AVAILABLE or PYTHON_LDAP_AVAILABLE


def _decode_attr(value):
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='ignore').strip()
    if isinstance(value, list) and value:
        return _decode_attr(value[0])
    return str(value).strip()


def authenticate_ad_user(username, password):
    """
    Validate AD credentials and return (user_dn, attrs dict) or (None, {}).

    Accepts sAMAccountName or email / UPN (user@domain).
    """
    if not username or not password:
        return None, {}

    login_id = username.strip().lower()
    if '\\' in login_id:
        login_id = login_id.split('\\', 1)[-1]

    server_uri = settings.LDAP_SERVER_URI
    base_dn = settings.LDAP_BASE_DN
    user_domain = getattr(settings, 'LDAP_USER_DOMAIN', 'kapa-oil.local')
    netbios = getattr(settings, 'LDAP_DOMAIN_NETBIOS', 'KAPA-OIL')

    if LDAP3_AVAILABLE:
        return _authenticate_ldap3(login_id, password, server_uri, base_dn, user_domain, netbios)
    if PYTHON_LDAP_AVAILABLE:
        return _authenticate_python_ldap(login_id, password, server_uri, base_dn, user_domain, netbios)
    logger.error('No LDAP library installed (pip install ldap3)')
    return None, {}


def _escape_ldap_filter(value):
    """Escape LDAP filter special characters."""
    return (
        value.replace('\\', r'\5c')
        .replace('*', r'\2a')
        .replace('(', r'\28')
        .replace(')', r'\29')
        .replace('\x00', r'\00')
    )


def _search_user_ldap3(conn, base_dn, username=None, email=None):
    attrs = [
        'sAMAccountName', 'mail', 'givenName', 'sn', 'title',
        'displayName', 'telephoneNumber', 'distinguishedName', 'userPrincipalName',
    ]
    if email:
        safe = _escape_ldap_filter(email)
        search_filter = (
            f'(&(objectClass=user)(objectCategory=person)'
            f'(|(mail={safe})(userPrincipalName={safe})))'
        )
    else:
        safe = _escape_ldap_filter(username or '')
        search_filter = f'(&(objectClass=user)(objectCategory=person)(sAMAccountName={safe}))'
    try:
        conn.search(base_dn, search_filter, attributes=attrs)
    except LDAPException as exc:
        logger.warning('LDAP search failed for %s/%s: %s', username, email, exc)
        return None, {}
    for entry in conn.entries:
        data = {}
        for attr in attrs:
            if hasattr(entry, attr):
                data[attr] = [str(getattr(entry, attr).value or '')]
        return entry.entry_dn, data
    return None, {}


def _minimal_attrs(username):
    return {
        'sAMAccountName': [username],
        'mail': [f'{username}@kapa-oil.local'],
        'givenName': [username],
        'sn': [''],
        'displayName': [username],
    }


def _lookup_user_with_service_account(server, base_dn, username=None, email=None):
    """Fetch profile attributes using the service account after a successful user bind."""
    bind_dn = (getattr(settings, 'LDAP_BIND_DN', '') or '').strip()
    bind_password = getattr(settings, 'LDAP_PASSWORD', '') or ''
    if not bind_dn or not bind_password:
        return None, {}
    try:
        conn = ldap3.Connection(
            server,
            user=bind_dn,
            password=bind_password,
            auto_bind=True,
            auto_referrals=False,
            receive_timeout=15,
        )
        user_dn, attrs = _search_user_ldap3(conn, base_dn, username=username, email=email)
        conn.unbind()
        return user_dn, attrs
    except Exception as exc:
        logger.warning('Service-account lookup failed for %s/%s: %s', username, email, exc)
        return None, {}


def _resolve_sam_account(server, base_dn, login_id):
    """
    If login_id is an email/UPN, resolve sAMAccountName via service account.
    Returns (sam, email_or_none).
    """
    if '@' not in login_id:
        return login_id, None

    user_dn, attrs = _lookup_user_with_service_account(server, base_dn, email=login_id)
    if attrs:
        sam = _decode_attr(attrs.get('sAMAccountName', [''])[0] if attrs.get('sAMAccountName') else '')
        if sam:
            return sam.lower(), login_id
    # Fallback: local-part before @
    return login_id.split('@', 1)[0], login_id


def _authenticate_ldap3(login_id, password, server_uri, base_dn, user_domain, netbios):
    server = ldap3.Server(server_uri, connect_timeout=15, get_info=ldap3.NONE)

    email_login = login_id if '@' in login_id else None
    sam, _ = _resolve_sam_account(server, base_dn, login_id)

    # Order: typed email/UPN, domain UPN, DOMAIN\user, NTLM
    attempts = []
    if email_login:
        attempts.append(('SIMPLE', email_login))
    attempts.extend([
        ('SIMPLE', f'{sam}@{user_domain}'),
        ('SIMPLE', f'{netbios}\\{sam}'),
        ('NTLM', f'{netbios}\\{sam}'),
    ])
    # de-dupe while preserving order
    seen = set()
    unique_attempts = []
    for mode, identity in attempts:
        key = (mode, identity.lower())
        if key not in seen:
            seen.add(key)
            unique_attempts.append((mode, identity))

    last_network_error = None
    for auth_mode, identity in unique_attempts:
        try:
            kwargs = {
                'user': identity,
                'password': password,
                'auto_bind': True,
                'auto_referrals': False,
                'receive_timeout': 15,
            }
            if auth_mode == 'NTLM' and NTLM is not None:
                kwargs['authentication'] = NTLM

            conn = ldap3.Connection(server, **kwargs)
            if not conn.bound:
                conn.unbind()
                continue

            # Password is correct. Prefer directory attributes when searchable.
            user_dn, attrs = _search_user_ldap3(conn, base_dn, username=sam)
            if not user_dn and email_login:
                user_dn, attrs = _search_user_ldap3(conn, base_dn, email=email_login)
            conn.unbind()

            if not user_dn:
                user_dn, attrs = _lookup_user_with_service_account(
                    server, base_dn, username=sam, email=email_login
                )

            if not user_dn:
                # Still authenticated — AD often blocks end-user directory search
                user_dn = f'CN={sam},{base_dn}'
                attrs = _minimal_attrs(sam)
                if email_login:
                    attrs['mail'] = [email_login]
                logger.info(
                    'LDAP bind OK for %s via %s but directory search empty; using minimal profile',
                    login_id, identity,
                )
            else:
                logger.info('LDAP bind OK for %s via %s', login_id, identity)

            return user_dn, attrs

        except LDAPSocketOpenError as exc:
            last_network_error = exc
            logger.error('LDAP server unreachable at %s: %s', server_uri, exc)
            break
        except LDAPBindError:
            logger.debug('LDAP bind failed for identity %s', identity)
            continue
        except LDAPException as exc:
            logger.warning('LDAP3 error for %s (%s): %s', identity, auth_mode, exc)
            continue
        except (ValueError, OSError, ImportError) as exc:
            # e.g. NTLM MD4 unavailable on some Python builds — try next mode
            logger.warning('LDAP auth attempt failed for %s (%s): %s', identity, auth_mode, exc)
            continue

    if last_network_error:
        return None, {}

    # Final fallback: service account search + verify user DN/password
    bind_dn = (getattr(settings, 'LDAP_BIND_DN', '') or '').strip()
    bind_password = getattr(settings, 'LDAP_PASSWORD', '') or ''
    if bind_dn and bind_password:
        try:
            conn = ldap3.Connection(
                server,
                user=bind_dn,
                password=bind_password,
                auto_bind=True,
                auto_referrals=False,
                receive_timeout=15,
            )
            user_dn, attrs = _search_user_ldap3(conn, base_dn, username=sam)
            if not user_dn and email_login:
                user_dn, attrs = _search_user_ldap3(conn, base_dn, email=email_login)
            conn.unbind()
            if user_dn:
                verify = ldap3.Connection(
                    server,
                    user=user_dn,
                    password=password,
                    auto_bind=True,
                    auto_referrals=False,
                    receive_timeout=15,
                )
                verify.unbind()
                return user_dn, attrs
        except LDAPBindError:
            logger.info('LDAP auth failed for %s: invalid credentials (service verify)', login_id)
        except LDAPSocketOpenError:
            logger.error('LDAP server unreachable at %s', server_uri)
        except LDAPException as exc:
            logger.error('LDAP3 service bind/verify error: %s', exc)

    return None, {}


def _authenticate_python_ldap(login_id, password, server_uri, base_dn, user_domain, netbios):
    conn = None
    try:
        conn = python_ldap.initialize(server_uri)
        conn.set_option(python_ldap.OPT_REFERRALS, 0)
        conn.set_option(python_ldap.OPT_NETWORK_TIMEOUT, 15)

        email_login = login_id if '@' in login_id else None
        sam = login_id.split('@', 1)[0]

        bind_identities = []
        if email_login:
            bind_identities.append(email_login)
        bind_identities.extend([f'{sam}@{user_domain}', f'{netbios}\\{sam}'])

        for identity in bind_identities:
            try:
                conn.simple_bind_s(identity, password)
                user_dn, attrs = _search_user_python_ldap(conn, base_dn, sam, email=email_login)
                if not user_dn:
                    user_dn = f'CN={sam},{base_dn}'
                    attrs = _minimal_attrs(sam)
                    if email_login:
                        attrs['mail'] = [email_login]
                return user_dn, attrs
            except python_ldap.INVALID_CREDENTIALS:
                continue

        if settings.LDAP_BIND_DN and settings.LDAP_PASSWORD:
            conn.simple_bind_s(settings.LDAP_BIND_DN, settings.LDAP_PASSWORD)
            user_dn, attrs = _search_user_python_ldap(conn, base_dn, sam, email=email_login)
            if user_dn:
                verify = python_ldap.initialize(server_uri)
                verify.set_option(python_ldap.OPT_REFERRALS, 0)
                verify.simple_bind_s(user_dn, password)
                verify.unbind_s()
                return user_dn, attrs

        return None, {}
    except python_ldap.INVALID_CREDENTIALS:
        logger.info('LDAP auth failed for %s: invalid credentials', login_id)
        return None, {}
    except python_ldap.SERVER_DOWN:
        logger.error('LDAP server unreachable at %s', server_uri)
        return None, {}
    except Exception as exc:
        logger.error('LDAP auth error for %s: %s', login_id, exc)
        return None, {}
    finally:
        if conn:
            try:
                conn.unbind_s()
            except Exception:
                pass


def _search_user_python_ldap(conn, base_dn, username, email=None):
    attrs = [
        'sAMAccountName', 'mail', 'givenName', 'sn', 'title',
        'displayName', 'telephoneNumber', 'distinguishedName', 'userPrincipalName',
    ]
    if email:
        safe = _escape_ldap_filter(email)
        search_filter = (
            f'(&(objectClass=user)(objectCategory=person)'
            f'(|(mail={safe})(userPrincipalName={safe})))'
        )
    else:
        safe = _escape_ldap_filter(username or '')
        search_filter = f'(&(objectClass=user)(objectCategory=person)(sAMAccountName={safe}))'
    results = conn.search_s(base_dn, python_ldap.SCOPE_SUBTREE, search_filter, attrs)
    for dn, entry_attrs in results:
        if entry_attrs:
            return dn, entry_attrs
    return None, {}


def decode_ldap_attrs(attrs, key):
    for attr_key in (key, key.encode() if isinstance(key, str) else key):
        if attr_key in attrs and attrs[attr_key]:
            val = attrs[attr_key][0]
            return _decode_attr(val)
    return ''


def diagnose_ldap(username=None, password=None):
    """
    Runtime diagnostics for admin/ops. Never logs the password.
    Returns a dict of checks.
    """
    from ldap3 import Server, Connection, NONE

    report = {
        'ldap_enabled': bool(getattr(settings, 'LDAP_ENABLED', False)),
        'library': 'ldap3' if LDAP3_AVAILABLE else ('python-ldap' if PYTHON_LDAP_AVAILABLE else 'none'),
        'server_uri': settings.LDAP_SERVER_URI,
        'base_dn': settings.LDAP_BASE_DN,
        'user_domain': getattr(settings, 'LDAP_USER_DOMAIN', ''),
        'netbios': getattr(settings, 'LDAP_DOMAIN_NETBIOS', ''),
        'bind_dn_set': bool((getattr(settings, 'LDAP_BIND_DN', '') or '').strip()),
        'bind_password_set': bool(getattr(settings, 'LDAP_PASSWORD', '') or ''),
        'bind_password_len': len(getattr(settings, 'LDAP_PASSWORD', '') or ''),
        'tcp_ok': False,
        'service_bind_ok': False,
        'user_bind_ok': None,
        'error': '',
    }

    if not LDAP3_AVAILABLE:
        report['error'] = 'ldap3 is not installed'
        return report

    try:
        from urllib.parse import urlparse
        import socket
        parsed = urlparse(settings.LDAP_SERVER_URI)
        host = parsed.hostname or '10.0.0.4'
        port = parsed.port or (636 if parsed.scheme == 'ldaps' else 389)
        with socket.create_connection((host, port), timeout=5):
            report['tcp_ok'] = True
    except Exception as exc:
        report['error'] = f'Cannot reach LDAP server: {exc}'
        return report

    bind_dn = (getattr(settings, 'LDAP_BIND_DN', '') or '').strip()
    bind_pw = getattr(settings, 'LDAP_PASSWORD', '') or ''
    if bind_dn and bind_pw:
        try:
            conn = Connection(
                Server(settings.LDAP_SERVER_URI, connect_timeout=10, get_info=NONE),
                user=bind_dn,
                password=bind_pw,
                auto_bind=True,
                auto_referrals=False,
                receive_timeout=10,
            )
            report['service_bind_ok'] = bool(conn.bound)
            conn.unbind()
        except Exception as exc:
            report['service_bind_ok'] = False
            report['error'] = f'Service bind failed: {type(exc).__name__}'

    if username and password:
        user_dn, _attrs = authenticate_ad_user(username, password)
        report['user_bind_ok'] = bool(user_dn)

    return report
