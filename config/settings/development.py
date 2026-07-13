from .base import *  # noqa: F401,F403

DEBUG = True
SERVE_MEDIA_PUBLICLY = True  # Dev only: local file preview via Django static helper

# ── Development email safety ──
# All artwork alerts, admin error emails, etc. go to this address only.
DEV_EMAIL_OVERRIDE = config(
    'DEV_EMAIL_OVERRIDE',
    default='support.user5@kapa-oil.com',
)
EMAIL_BACKEND = 'config.email_backends.DevelopmentRedirectEmailBackend'
ADMINS = [('Support', DEV_EMAIL_OVERRIDE)]
SERVER_EMAIL = DEV_EMAIL_OVERRIDE
