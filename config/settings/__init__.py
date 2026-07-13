import os

env = os.environ.get('DJANGO_SETTINGS_MODULE', 'config.settings.development')
if env.endswith('production'):
    from .production import *  # noqa: F401,F403
else:
    from .development import *  # noqa: F401,F403
