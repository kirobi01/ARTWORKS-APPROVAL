# users/models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Role(models.Model):
    """Define user roles with specific permissions"""
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=20, unique=True)  
    description = models.TextField(blank=True)
    level = models.IntegerField(default=1)
    
    def __str__(self):
        return self.name

class Profile(models.Model):
    """Enhanced user profile with role-based access"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    roles = models.ManyToManyField(Role, related_name='profiles')
    department = models.CharField(max_length=100, blank=True)
    email = models.EmailField(max_length=254, default='support.user5@kapa-oil.com')
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['user__username']
    
    def __str__(self):
        return f'{self.user.username} Profile'
    
    def has_role(self, role_code):
        return self.roles.filter(code=role_code).exists()
    
    def get_highest_level(self):
        return self.roles.aggregate(models.Max('level'))['level__max'] or 0

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