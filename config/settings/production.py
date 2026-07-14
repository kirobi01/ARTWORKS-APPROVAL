from .base import *  # noqa: F401,F403

DEBUG = False
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'true').lower() == 'true'
# Keep False for plain HTTP docker/nginx until TLS is in front
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000' if SECURE_SSL_REDIRECT else '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_SSL_REDIRECT
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if o.strip()
]

SERVE_MEDIA_PUBLICLY = False

if USE_S3:
    INSTALLED_APPS += ['storages']  # noqa: F405
    STORAGES = {
        'default': {
            'BACKEND': 'artwork.storage_backends.PrivateMediaStorage',
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/' if AWS_S3_CUSTOM_DOMAIN else '/media/'  # noqa: F405
else:
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
