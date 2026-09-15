from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AgencyProfile, CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('AutoLease roles', {'fields': ('is_renter', 'is_agency')}),
    )
    list_display = ('username', 'email', 'is_renter', 'is_agency', 'is_staff')


@admin.register(AgencyProfile)
class AgencyProfileAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'user', 'contact_number')
    search_fields = ('business_name', 'user__email')
