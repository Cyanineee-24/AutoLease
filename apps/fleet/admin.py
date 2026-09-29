from django.contrib import admin

from .models import Favorite, Vehicle, VehicleImage


class VehicleImageInline(admin.TabularInline):
    model = VehicleImage
    extra = 1


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('plate_number', 'make', 'model', 'city', 'status', 'daily_rate', 'agency')
    list_filter = ('status', 'city')
    search_fields = ('plate_number', 'make', 'model', 'city')
    raw_id_fields = ('agency',)
    inlines = [VehicleImageInline]


@admin.register(VehicleImage)
class VehicleImageAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'is_primary', 'sort_order', 'uploaded_at')
    list_filter = ('is_primary',)
    raw_id_fields = ('vehicle',)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'vehicle', 'created_at')
    raw_id_fields = ('user', 'vehicle')
