"""
Shared Django settings for the Artwork Approval System.
"""
from pathlib import Path
import os
from datetime import timedelta

try:
    from celery.schedules import crontab  # type: ignore
except Exception:  # pragma: no cover
    def crontab(*args, **kwargs):
        return None

from users.ldap_client import ldap_is_available

from config.env import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-in-production')

DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = [
    h.strip()
    for h in config(
        'ALLOWED_HOSTS',
        default='127.0.0.1,localhost,10.0.0.7,10.10.1.18,Kapa-apps-07,ICTSUPPORT5.kapa-oil.local,ictsupport5.kapa-oil.local',
    ).split(',')
    if h.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'users.apps.UsersConfig',
    'artwork.apps.ArtworkConfig',
    'rest_framework',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'artwork' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'artwork.context_processors.artwork_nav',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DB_ENGINE = config('DB_ENGINE', default='postgres')

if str(DB_ENGINE).lower() in {'postgres', 'postgresql', 'psql', 'django.db.backends.postgresql'}:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='RMTR'),
            'USER': config('DB_USER', default='admin'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='127.0.0.1'),
            'PORT': config('DB_PORT', default='5432'),
            'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=60, cast=int),
            'OPTIONS': {
                'sslmode': config('DB_SSLMODE', default='prefer'),
            },
        }
    }
else:
    raise ValueError('Only PostgreSQL is supported. Set DB_ENGINE=postgres.')

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = False

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/artwork/login/'
LOGIN_REDIRECT_URL = '/artwork/dashboard/'
LOGOUT_REDIRECT_URL = '/artwork/login/'

SITE_URL = config('SITE_URL', default='http://127.0.0.1:8000')

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='10.0.0.25')
EMAIL_PORT = config('EMAIL_PORT', default=25, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='kapaportal@kapa-oil.local')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='kapaportal@kapa-oil.local')
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=10, cast=int)

LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

_LOG_PID_SUFFIX = f'-{os.getpid()}' if (os.name == 'nt' and DEBUG) else ''
APP_LOG_FILENAME = str(LOGS_DIR / f'artwork{_LOG_PID_SUFFIX}.log')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {name} {funcName}:{lineno} {message}',
            'style': '{',
        },
        'simple': {'format': '{levelname} {message}', 'style': '{'},
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': APP_LOG_FILENAME,
            'maxBytes': 10485760,
            'backupCount': 10,
            'delay': True,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
        },
    },
    'loggers': {
        'artwork': {
            'handlers': ['file', 'console', 'mail_admins'],
            'level': 'INFO',
            'propagate': False,
        },
        'users': {
            'handlers': ['file', 'console', 'mail_admins'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

WKHTMLTOPDF_PATH = config(
    'WKHTMLTOPDF_PATH',
    default=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
)

CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Africa/Nairobi'

CELERY_BEAT_SCHEDULE = {
    'check-artwork-deadlines': {
        'task': 'artwork.tasks.check_artwork_deadlines',
        'schedule': timedelta(minutes=15),
    },
    'sync-ldap-users-0730': {
        'task': 'sync_ldap_users',
        'schedule': crontab(hour=7, minute=30),
    },
    'sync-ldap-users-1330': {
        'task': 'sync_ldap_users',
        'schedule': crontab(hour=13, minute=30),
    },
}

# ── LDAP / Active Directory ──
LDAP_SERVER_URI = config('LDAP_SERVER_URI', default='ldap://10.0.0.4:389')
LDAP_BIND_DN = config('LDAP_BIND_DN', default='')
LDAP_PASSWORD = config('LDAP_PASSWORD', default='')
LDAP_BASE_DN = config('LDAP_BASE_DN', default='DC=kapa-oil,DC=local')
LDAP_USER_DOMAIN = config('LDAP_USER_DOMAIN', default='kapa-oil.local')
LDAP_DOMAIN_NETBIOS = config('LDAP_DOMAIN_NETBIOS', default='KAPA-OIL')
LDAP_ENABLED = config('LDAP_ENABLED', default=True, cast=bool)

OU_TO_DEPARTMENT_MAP = {
    'IT': {'name': 'Information Technology', 'code': 'IT'},
    'HR': {'name': 'Human Resources', 'code': 'HR'},
    'Finance': {'name': 'Finance Department', 'code': 'FIN'},
    'Sales': {'name': 'Sales Department', 'code': 'SALES'},
    'Marketing': {'name': 'Marketing Department', 'code': 'MKT'},
    'Design': {'name': 'Design', 'code': 'DESIGN'},
    'Quality Assurance': {'name': 'Quality Assurance', 'code': 'QA'},
    'Operations': {'name': 'Operations', 'code': 'OPS'},
    'Procurement': {'name': 'Procurement', 'code': 'PROC'},
}

AUTHENTICATION_BACKENDS = [
    'users.authentication.FlexibleUsernameBackend',
    'django.contrib.auth.backends.ModelBackend',
]

if ldap_is_available() and LDAP_ENABLED:
    AUTHENTICATION_BACKENDS.insert(0, 'users.authentication.LDAPAuthenticationBackend')

# Media is always served through authenticated views — never public direct URLs.
SERVE_MEDIA_PUBLICLY = False

USE_S3 = config('USE_S3', default=False, cast=bool)

AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
AWS_S3_ENDPOINT_URL = config('AWS_S3_ENDPOINT_URL', default='') or None
AWS_S3_CUSTOM_DOMAIN = config('AWS_S3_CUSTOM_DOMAIN', default='') or None
AWS_S3_SIGNATURE_VERSION = 's3v4'
AWS_DEFAULT_ACL = 'private'
AWS_QUERYSTRING_AUTH = True
AWS_S3_FILE_OVERWRITE = False
AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}

MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
(BASE_DIR / 'media' / 'artwork').mkdir(parents=True, exist_ok=True)
