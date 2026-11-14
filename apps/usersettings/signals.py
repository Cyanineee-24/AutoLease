from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserSettings


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid='usersettings_create_settings')
def create_user_settings(sender, instance, created, raw, **kwargs):
    """Every user gets exactly one UserSettings row (ERD). Skipped for fixture loads."""
    if created and not raw:
        UserSettings.objects.get_or_create(user=instance)
