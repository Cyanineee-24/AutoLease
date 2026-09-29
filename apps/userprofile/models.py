from django.conf import settings
from django.db import models

# Deliberately omitting full_name because CustomUser already stores first_name/last_name
class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    bio = models.TextField(blank=True)
    profile_image = models.ImageField(
        upload_to='userprofile/',
        blank=True,
        null=True,
    )

    def __str__(self):
        return f'Profile for {self.user}'


class DriverLicense(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='driver_license',
    )
    license_number = models.CharField(max_length=50)
    issuing_country = models.CharField(max_length=100)
    expiry_date = models.DateField()
    license_image = models.ImageField(upload_to='userprofile/licenses/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'License {self.license_number} ({self.user})'
