from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    contact_number = models.CharField(max_length=50, blank=True)
    is_renter = models.BooleanField(default=False)
    is_agency = models.BooleanField(default=False)

    def __str__(self):
        return self.email


class AgencyProfile(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='agency_profile',
    )
    business_name = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=50)

    def __str__(self):
        return self.business_name
