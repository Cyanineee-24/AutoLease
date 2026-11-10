from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.fleet.models import Vehicle
from apps.userprofile.models import DriverLicense

from .forms import BookingRequestForm


def _detail_url(vehicle, start='', end=''):
    url = reverse('fleet:vehicle_detail', args=[vehicle.pk])
    params = {k: v for k, v in (('start_date', start), ('end_date', end)) if v}
    return f'{url}?{urlencode(params)}' if params else url


@login_required
@require_POST
def booking_request(request, vehicle_pk):
    vehicle = get_object_or_404(
        Vehicle.objects.select_related('agency'), pk=vehicle_pk, status='available'
    )
    start = request.POST.get('start_date', '')
    end = request.POST.get('end_date', '')

    if vehicle.agency.user_id == request.user.pk:
        messages.error(request, "You can't request your own car.")
        return redirect(_detail_url(vehicle, start, end))

    if not DriverLicense.objects.filter(user=request.user).exists():
        messages.error(
            request, "Add your driver's license to your profile before requesting a car."
        )
        return redirect(_detail_url(vehicle, start, end))

    form = BookingRequestForm(request.POST, vehicle=vehicle, renter=request.user)
    if not form.is_valid():
        for error in form.non_field_errors():
            messages.error(request, error)
        for field in ('start_date', 'end_date', 'renter_message'):
            for error in form.errors.get(field, []):
                messages.error(request, f'{form.fields[field].label}: {error}')
        return redirect(_detail_url(vehicle, start, end))

    booking = form.save(commit=False)
    booking.renter = request.user
    booking.vehicle = vehicle
    booking.daily_rate_snapshot = vehicle.daily_rate
    booking.status = 'pending'
    try:
        with transaction.atomic():
            booking.save()
    except IntegrityError:
        messages.error(request, 'Those dates are no longer available. Please pick other dates.')
        return redirect(_detail_url(vehicle, start, end))

    days = (booking.end_date - booking.start_date).days + 1
    messages.success(
        request,
        f'Request sent for {days} day{"s" if days != 1 else ""}. '
        'The agency will approve or decline it soon.',
    )
    return redirect('mybookings:list')
