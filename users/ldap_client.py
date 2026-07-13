"""LDAP helpers — uses ldap3 (Windows-friendly) with optional python-ldap fallback."""
import logging

from django.conf import settings

logger = logging.getLogger('users')

try:
    import ldap3
    from ldap3.core.exceptions import LDAPBindError, LDAPException, LDAPSocketOpenError
    LDAP3_AVAILABLE = True
except ImportError:
    ldap3 = None
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
    """
    if not username or not password:
        return None, {}

    username = username.strip().lower()
    server_uri = settings.LDAP_SERVER_URI
    base_dn = settings.LDAP_BASE_DN
    user_domain = getattr(settings, 'LDAP_USER_DOMAIN', 'kapa-oil.local')
    netbios = getattr(settings, 'LDAP_DOMAIN_NETBIOS', 'KAPA-OIL')

    if LDAP3_AVAILABLE:
        return _authenticate_ldap3(username, password, server_uri, base_dn, user_domain, netbios)
    if PYTHON_LDAP_AVAILABLE:
        return _authenticate_python_ldap(username, password, server_uri, base_dn, user_domain, netbios)
    logger.error('No LDAP library installed (pip install ldap3)')
    return None, {}


def _search_user_ldap3(conn, base_dn, username):
    search_filter = f'(&(objectClass=user)(objectCategory=person)(sAMAccountName={username}))'
    attrs = [
        'sAMAccountName', 'mail', 'givenName', 'sn', 'title',
        'displayName', 'telephoneNumber', 'distinguishedName',
    ]
    conn.search(base_dn, search_filter, attributes=attrs)
    for entry in conn.entries:
        data = {}
        for attr in attrs:
            if hasattr(entry, attr):
                data[attr] = [str(getattr(entry, attr).value or '')]
        return entry.entry_dn, data
    return None, {}


def _authenticate_ldap3(username, password, server_uri, base_dn, user_domain, netbios):
    server = ldap3.Server(server_uri, connect_timeout=15, get_info=ldap3.NONE)
    bind_identities = [
        f'{username}@{user_domain}',
        f'{netbios}\\{username}',
    ]

    for identity in bind_identities:
        try:
            conn = ldap3.Connection(server, user=identity, password=password, auto_bind=True)
            user_dn, attrs = _search_user_ldap3(conn, base_dn, username)
            conn.unbind()
            if user_dn:
                return user_dn, attrs
        except (LDAPBindError, LDAPSocketOpenError):
            continue
        except LDAPException as exc:
            logger.warning('LDAP3 bind error for %s: %s', identity, exc)
            continue

    bind_dn = getattr(settings, 'LDAP_BIND_DN', '')
    bind_password = getattr(settings, 'LDAP_PASSWORD', '')
    if bind_dn and bind_password:
        try:
            conn = ldap3.Connection(server, user=bind_dn, password=bind_password, auto_bind=True)
            user_dn, attrs = _search_user_ldap3(conn, base_dn, username)
            if user_dn:
                verify = ldap3.Connection(server, user=user_dn, password=password, auto_bind=True)
                verify.unbind()
            conn.unbind()
            if user_dn:
                return user_dn, attrs
        except LDAPBindError:
            logger.info('LDAP auth failed for %s: invalid credentials', username)
        except LDAPSocketOpenError:
            logger.error('LDAP server unreachable at %s', server_uri)
        except LDAPException as exc:
            logger.error('LDAP3 service bind error: %s', exc)

    return None, {}


def _authenticate_python_ldap(username, password, server_uri, base_dn, user_domain, netbios):
    conn = None
    try:
        conn = python_ldap.initialize(server_uri)
        conn.set_option(python_ldap.OPT_REFERRALS, 0)
        conn.set_option(python_ldap.OPT_NETWORK_TIMEOUT, 15)

        user_dn = None
        attrs = {}
        bind_identities = [f'{username}@{user_domain}', f'{netbios}\\{username}']
        for identity in bind_identities:
            try:
                conn.simple_bind_s(identity, password)
                user_dn, attrs = _search_user_python_ldap(conn, base_dn, username)
                if user_dn:
                    break
            except python_ldap.INVALID_CREDENTIALS:
                continue

        if not user_dn and settings.LDAP_BIND_DN and settings.LDAP_PASSWORD:
            conn.simple_bind_s(settings.LDAP_BIND_DN, settings.LDAP_PASSWORD)
            user_dn, attrs = _search_user_python_ldap(conn, base_dn, username)
            if user_dn:
                verify = python_ldap.initialize(server_uri)
                verify.set_option(python_ldap.OPT_REFERRALS, 0)
                verify.simple_bind_s(user_dn, password)
                verify.unbind_s()

        return user_dn, attrs
    except python_ldap.INVALID_CREDENTIALS:
        logger.info('LDAP auth failed for %s: invalid credentials', username)
        return None, {}
    except python_ldap.SERVER_DOWN:
        logger.error('LDAP server unreachable at %s', server_uri)
        return None, {}
    except Exception as exc:
        logger.error('LDAP auth error for %s: %s', username, exc)
        return None, {}
    finally:
        if conn:
            try:
                conn.unbind_s()
            except Exception:
                pass


def _search_user_python_ldap(conn, base_dn, username):
    search_filter = f'(&(objectClass=user)(objectCategory=person)(sAMAccountName={username}))'
    attrs = [
        'sAMAccountName', 'mail', 'givenName', 'sn', 'title',
        'displayName', 'telephoneNumber', 'distinguishedName',
    ]
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
