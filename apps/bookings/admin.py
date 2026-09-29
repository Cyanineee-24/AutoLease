from django.contrib import admin

from .models import Booking, Review


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'renter', 'vehicle', 'start_date', 'end_date', 'status', 'daily_rate_snapshot', 'created_at')
    list_filter = ('status',)
    search_fields = ('renter__email', 'renter__username', 'vehicle__plate_number')
    raw_id_fields = ('renter', 'vehicle')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('booking', 'rating', 'created_at')
    list_filter = ('rating',)
    raw_id_fields = ('booking',)
