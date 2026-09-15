from django.conf import settings
from django.db import models


class UserSettings(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='settings',
    )
    email_notifications = models.BooleanField(default=True)
    marketing_emails = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    show_contact_number = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'user settings'

    def __str__(self):
        return f'Settings for {self.user}'
