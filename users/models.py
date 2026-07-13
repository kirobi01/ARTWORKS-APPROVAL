# users/models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from users.account_utils import normalize_username


class LDAPSyncLog(models.Model):
    """Audit trail for AD sync operations triggered from admin or Celery."""
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='ldap_syncs'
    )
    dry_run = models.BooleanField(default=False)
    update_existing = models.BooleanField(default=True)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    errors_count = models.PositiveIntegerField(default=0)
    total_ldap_entries = models.PositiveIntegerField(default=0)
    success = models.BooleanField(default=False)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'Sync {self.started_at:%Y-%m-%d %H:%M} — {self.message[:60]}'


class Role(models.Model):
    """Define user roles with specific permissions"""
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=20, unique=True)  
    description = models.TextField(blank=True)
    level = models.IntegerField(default=1)
    
    def __str__(self):
        return self.name

class Profile(models.Model):
    """Enhanced user profile with LDAP/AD metadata."""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    roles = models.ManyToManyField(Role, related_name='profiles', blank=True)
    department = models.CharField(max_length=100, blank=True)
    email = models.EmailField(max_length=254, blank=True)
    position = models.CharField(max_length=150, blank=True)
    extension_no = models.CharField(max_length=30, blank=True)
    ldap_dn = models.CharField(max_length=512, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['user__username']
    
    def __str__(self):
        return f'{self.user.username} Profile'
    
    def has_role(self, role_code):
        return self.roles.filter(code=role_code).exists()
    
    def get_highest_level(self):
        return self.roles.aggregate(models.Max('level'))['level__max'] or 0


@receiver(pre_save, sender=User)
def normalize_user_username(sender, instance, **kwargs):
    if instance.username:
        instance.username = normalize_username(instance.username)


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """Create or update user profile"""
    if created:
        Profile.objects.create(user=instance)
    else:
        # Get or create profile for existing users
        Profile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save the user profile"""
    try:
        if not hasattr(instance, 'profile'):
            # Create profile if it doesn't exist
            Profile.objects.create(user=instance)
        instance.profile.save()
    except Profile.DoesNotExist:
        # Create profile if it doesn't exist
        Profile.objects.create(user=instance)
    except Exception as e:
        print(f"Error saving profile for user {instance.username}: {str(e)}")