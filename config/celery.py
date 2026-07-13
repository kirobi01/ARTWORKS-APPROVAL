import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.development'

from celery import Celery

app = Celery('artwork')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
