from django.contrib import admin

from .models import DriverLicense, Profile

# Register your models here.


@admin.register(DriverLicense)
class DriverLicenseAdmin(admin.ModelAdmin):
    list_display = ('user', 'license_number', 'issuing_country', 'expiry_date', 'created_at')
    search_fields = ('license_number', 'user__email', 'user__username')
    raw_id_fields = ('user',)
