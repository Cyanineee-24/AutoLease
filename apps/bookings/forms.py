from django import forms
from django.utils import timezone

from .models import Booking


class BookingRequestForm(forms.ModelForm):
    """Renter's date-range request for a single vehicle."""

    class Meta:
        model = Booking
        fields = ['start_date', 'end_date', 'renter_message']

    def __init__(self, *args, vehicle=None, renter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.vehicle = vehicle
        self.renter = renter
        self.fields['renter_message'].required = False
        self.fields['renter_message'].max_length = 1000

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if not start or not end:
            return cleaned

        if start < timezone.localdate():
            raise forms.ValidationError('Pick-up date cannot be in the past.')
        if end < start:
            raise forms.ValidationError('Drop-off must be on or after pick-up.')

        # Inclusive date ranges overlap when start <= other_end and end >= other_start.
        overlapping = Booking.objects.filter(
            vehicle=self.vehicle,
            start_date__lte=end,
            end_date__gte=start,
        )
        if overlapping.filter(status='approved').exists():
            raise forms.ValidationError(
                'This car is already booked for some of those dates.'
            )
        if overlapping.filter(renter=self.renter, status='pending').exists():
            raise forms.ValidationError(
                'You already have a pending request for these dates.'
            )
        return cleaned
