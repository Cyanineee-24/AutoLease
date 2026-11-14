from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import agency_required
from apps.bookings.lifecycle import AGENCY_CANCEL_PREFIX, display_status, trip_phase
from apps.bookings.models import Booking

from .forms import CancelTripForm, DecisionForm

AUTO_DECLINE_RESPONSE = 'Dates no longer available'


def _renter_name(user):
    return (user.first_name or '').strip() or 'Renter'


@login_required
@agency_required
def inbox(request):
    bookings = list(
        Booking.objects.filter(vehicle__agency__user=request.user)
        .select_related('vehicle', 'renter')
        .order_by('start_date', 'created_at')
    )
    today = timezone.localdate()
    for booking in bookings:
        booking.status_key, booking.status_label = display_status(booking, today)
        booking.phase = trip_phase(booking, today)
        booking.days = (booking.end_date - booking.start_date).days + 1
        booking.total = booking.daily_rate_snapshot * booking.days
        booking.renter_name = _renter_name(booking.renter)

    pending = [b for b in bookings if b.status == 'pending']
    # Upcoming and in-progress trips; already sorted by start_date above.
    active = [b for b in bookings if b.status == 'approved' and b.end_date >= today]
    active_ids = {b.pk for b in active}
    history = sorted(
        (b for b in bookings if b.status != 'pending' and b.pk not in active_ids),
        key=lambda b: b.decided_at or b.updated_at,
        reverse=True,
    )
    context = {'pending': pending, 'active': active, 'history': history}
    return render(request, 'agencyrequests/inbox.html', context)


@login_required
@agency_required
@require_POST
def decide(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related('vehicle'),
        pk=pk,
        vehicle__agency__user=request.user,
    )
    form = DecisionForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Choose approve or decline. Replies are limited to 1000 characters.')
        return redirect('agencyrequests:inbox')
    if booking.status != 'pending':
        messages.error(request, 'This request has already been decided.')
        return redirect('agencyrequests:inbox')

    action = form.cleaned_data['action']
    if action == 'approve' and booking.vehicle.status != 'available':
        messages.error(request, 'This car is not available right now. Set it to Available in My listings first.')
        return redirect('agencyrequests:inbox')

    now = timezone.now()
    booking.agency_response = form.cleaned_data['agency_response']
    booking.decided_at = now
    vehicle_name = f'{booking.vehicle.make} {booking.vehicle.model}'

    if action == 'decline':
        booking.status = 'declined'
        booking.save(update_fields=['status', 'agency_response', 'decided_at', 'updated_at'])
        messages.success(request, f'Declined the request for the {vehicle_name}.')
        return redirect('agencyrequests:inbox')

    booking.status = 'approved'
    try:
        with transaction.atomic():
            booking.save(update_fields=['status', 'agency_response', 'decided_at', 'updated_at'])
            auto_declined = (
                Booking.objects.filter(
                    vehicle=booking.vehicle,
                    status='pending',
                    start_date__lte=booking.end_date,
                    end_date__gte=booking.start_date,
                )
                .exclude(pk=booking.pk)
                .update(
                    status='declined',
                    agency_response=AUTO_DECLINE_RESPONSE,
                    decided_at=now,
                    updated_at=now,
                )
            )
    except IntegrityError:
        messages.error(
            request,
            f'Could not approve: the {vehicle_name} is already booked for some of those dates.',
        )
        return redirect('agencyrequests:inbox')

    note = f' {auto_declined} overlapping request{"s were" if auto_declined != 1 else " was"} declined automatically.' if auto_declined else ''
    messages.success(request, f'Approved the request for the {vehicle_name}.{note}')
    return redirect('agencyrequests:inbox')


@login_required
@agency_required
@require_POST
def cancel_trip(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related('vehicle', 'renter'),
        pk=pk,
        vehicle__agency__user=request.user,
    )
    today = timezone.localdate()
    if booking.status != 'approved':
        messages.error(request, 'Only upcoming trips can be cancelled.')
        return redirect('agencyrequests:inbox')
    if today >= booking.start_date:
        messages.error(request, "This trip has already started, so it can't be cancelled.")
        return redirect('agencyrequests:inbox')

    form = CancelTripForm(request.POST)
    if not form.is_valid():
        messages.error(request, form.errors['reason'][0])
        return redirect('agencyrequests:inbox')

    # decided_at stays as the approval time. The no-overlap constraint only
    # covers approved bookings, so this frees the dates.
    booking.status = 'cancelled'
    booking.agency_response = AGENCY_CANCEL_PREFIX + form.cleaned_data['reason']
    booking.save(update_fields=['status', 'agency_response', 'updated_at'])

    messages.success(
        request,
        f"Cancelled {_renter_name(booking.renter)}'s trip in the "
        f'{booking.vehicle.make} {booking.vehicle.model}. The dates are open again.',
    )
    return redirect('agencyrequests:inbox')
