from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_workflow_groups(sender, **kwargs):
    """Ensure the workflow access groups exist so they can be granted in admin."""
    from django.contrib.auth.models import Group
    from .config import GROUP_STATUS_MAPPING
    for name in GROUP_STATUS_MAPPING:
        Group.objects.get_or_create(name=name)


class ArtworkConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'artwork'
    verbose_name = 'Artwork Approval'

    def ready(self):
        post_migrate.connect(_seed_workflow_groups, sender=self)
