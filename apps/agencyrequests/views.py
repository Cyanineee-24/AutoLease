from collections import defaultdict
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.http import require_POST

from apps.accounts.decorators import agency_required
from apps.bookings.lifecycle import (
    AGENCY_CANCEL_PREFIX,
    agency_cancel_reason,
    display_status,
    trip_phase,
)
from apps.bookings.models import Booking
from apps.bookings.notifications import notify_cancelled_by_agency, notify_decision
from apps.fleet.models import Vehicle
from apps.usersettings.models import UserSettings

from .forms import CancelTripForm, DecisionForm

AUTO_DECLINE_RESPONSE = 'Dates no longer available'

# Filter chips, in display order. 'past' groups everything that is over.
STATUS_FILTERS = [
    ('all', 'All'),
    ('pending', 'Pending'),
    ('upcoming', 'Upcoming'),
    ('in_progress', 'In progress'),
    ('past', 'Past'),
]
# display_status() key -> filter group.
STATUS_GROUPS = {
    'pending': 'pending',
    'upcoming': 'upcoming',
    'in_progress': 'in_progress',
    'completed': 'past',
    'declined': 'past',
    'cancelled': 'past',
}
SORT_CHOICES = [('newest', 'Newest first'), ('pickup', 'Pick-up date')]


def _renter_name(user):
    return (user.first_name or '').strip() or 'Renter'


def _overlaps(first, second):
    """Inclusive date ranges, the same rule decide() and the booking form use."""
    return first.start_date <= second.end_date and first.end_date >= second.start_date


def _short_range(start, end):
    """'Nov 21 – 26', 'Nov 28 – Dec 2', or with years when they differ."""
    if start.year != end.year:
        return f'{date_format(start, "M j, Y")} – {date_format(end, "M j, Y")}'
    if start.month != end.month:
        return f'{date_format(start, "M j")} – {date_format(end, "M j")}'
    if start == end:
        return date_format(start, 'M j')
    return f'{date_format(start, "M j")} – {end.day}'


def _join_with_and(parts):
    """['A'] -> 'A'; ['A', 'B'] -> 'A and B'; ['A', 'B', 'C'] -> 'A, B and C'."""
    if len(parts) <= 1:
        return ''.join(parts)
    return f'{", ".join(parts[:-1])} and {parts[-1]}'


def _approve_confirm_text(booking, others):
    declined = _join_with_and([
        f'{other.renter_name} ({_short_range(other.start_date, other.end_date)})' for other in others
    ])
    return (
        f'Approving {booking.renter_name} automatically declines {declined}. '
        "They'll be told the dates are no longer available."
    )


def _mark_overlaps(bookings):
    """Tell each pending request what approving it would run into.

    Works on the bookings already loaded, so it adds no queries.
    - overlapping_pending: the other pending requests decide() would auto-decline.
    - blocking_trip: an approved trip on the same car and dates, which makes
      approval impossible (the database constraint would refuse it).
    """
    by_vehicle = defaultdict(list)
    for booking in bookings:
        by_vehicle[booking.vehicle_id].append(booking)

    for booking in bookings:
        booking.overlapping_pending = []
        booking.blocking_trip = None
        booking.clash_text = ''
        booking.approve_confirm_text = ''
        if booking.status != 'pending':
            continue
        same_car = [other for other in by_vehicle[booking.vehicle_id] if other.pk != booking.pk and _overlaps(booking, other)]
        booking.overlapping_pending = sorted(
            (other for other in same_car if other.status == 'pending'),
            key=lambda other: (other.start_date, other.pk),
        )
        booking.blocking_trip = next((other for other in same_car if other.status == 'approved'), None)
        if booking.blocking_trip:
            trip = booking.blocking_trip
            booking.clash_text = (
                f"Clashes with {trip.renter_name}'s approved trip on "
                f'{_short_range(trip.start_date, trip.end_date)}. '
                'Decline this request, or cancel that trip first.'
            )
        elif booking.overlapping_pending:
            booking.approve_confirm_text = _approve_confirm_text(booking, booking.overlapping_pending)


def _inbox_url(status, car, sort):
    """The inbox URL for one combination of filters; defaults are left out."""
    params = {}
    if status != 'all':
        params['status'] = status
    if car:
        params['car'] = car
    if sort != 'newest':
        params['sort'] = sort
    base = reverse('agencyrequests:inbox')
    return f'{base}?{urlencode(params)}' if params else base


@login_required
@agency_required
def inbox(request):
    # One query for every booking of this agency; filtering and sorting happen in Python.
    bookings = list(
        Booking.objects.filter(vehicle__agency__user=request.user)
        .select_related('vehicle', 'renter')
        .order_by('-created_at', '-pk')
    )
    cars = list(Vehicle.objects.filter(agency__user=request.user).order_by('make', 'model', 'year', 'pk'))

    # One query for every renter's privacy choice. A missing settings row means
    # the default (shown), the same rule fleet/views.py uses for agencies.
    hidden_contact_ids = set(
        UserSettings.objects.filter(
            user_id__in={b.renter_id for b in bookings},
            show_contact_number=False,
        ).values_list('user_id', flat=True)
    )
    today = timezone.localdate()
    for booking in bookings:
        booking.renter_contact = (
            '' if booking.renter_id in hidden_contact_ids else booking.renter.contact_number or ''
        )
        booking.status_key, booking.status_label = display_status(booking, today)
        booking.group = STATUS_GROUPS.get(booking.status_key, 'past')
        booking.phase = trip_phase(booking, today)
        booking.days = (booking.end_date - booking.start_date).days + 1
        booking.total = booking.daily_rate_snapshot * booking.days
        booking.renter_name = _renter_name(booking.renter)
        # Shown on past cards. The stored "Cancelled by the agency: " prefix is never displayed.
        booking.cancel_reason = agency_cancel_reason(booking)
    _mark_overlaps(bookings)

    # Filters. Unknown values fall back quietly; a car that isn't this agency's is ignored.
    current_status = request.GET.get('status', 'all')
    if current_status not in dict(STATUS_FILTERS):
        current_status = 'all'
    current_sort = request.GET.get('sort', 'newest')
    if current_sort not in dict(SORT_CHOICES):
        current_sort = 'newest'
    car_param = request.GET.get('car', '')
    current_car = int(car_param) if car_param.isdecimal() and int(car_param) in {c.pk for c in cars} else None

    # Chip counts respect the car filter, not the status filter.
    in_scope = [b for b in bookings if current_car is None or b.vehicle_id == current_car]
    status_counts = {key: 0 for key, _ in STATUS_FILTERS}
    status_counts['all'] = len(in_scope)
    for booking in in_scope:
        status_counts[booking.group] += 1

    visible = [b for b in in_scope if current_status == 'all' or b.group == current_status]
    if current_sort == 'pickup':
        visible.sort(key=lambda b: (b.start_date, b.created_at))

    context = {
        'bookings': visible,
        'status_counts': status_counts,
        'status_filters': [
            {
                'key': key,
                'label': label,
                'count': status_counts[key],
                'url': _inbox_url(key, current_car, current_sort),
                'active': key == current_status,
            }
            for key, label in STATUS_FILTERS
        ],
        'cars': cars,
        'sort_choices': SORT_CHOICES,
        'current_status': current_status,
        'current_car': current_car,
        'current_sort': current_sort,
        'has_filters': current_status != 'all' or current_car is not None,
        # The subtitle counts everything, whatever the filters.
        'total_count': len(bookings),
        'pending_total': sum(1 for b in bookings if b.group == 'pending'),
        'active_total': sum(1 for b in bookings if b.group in ('upcoming', 'in_progress')),
    }
    return render(request, 'agencyrequests/inbox.html', context)


@login_required
@agency_required
@require_POST
def decide(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related('vehicle__agency', 'renter'),
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
        notify_decision(booking, request)
        messages.success(request, f'Declined the request for the {vehicle_name}.')
        return redirect('agencyrequests:inbox')

    booking.status = 'approved'
    try:
        with transaction.atomic():
            booking.save(update_fields=['status', 'agency_response', 'decided_at', 'updated_at'])
            # Ids first, so the emails go to exactly the bookings this update declines.
            overlapping_ids = list(
                Booking.objects.filter(
                    vehicle=booking.vehicle,
                    status='pending',
                    start_date__lte=booking.end_date,
                    end_date__gte=booking.start_date,
                )
                .exclude(pk=booking.pk)
                .values_list('pk', flat=True)
            )
            auto_declined = Booking.objects.filter(pk__in=overlapping_ids, status='pending').update(
                status='declined',
                agency_response=AUTO_DECLINE_RESPONSE,
                decided_at=now,
                updated_at=now,
            )
    except IntegrityError:
        messages.error(
            request,
            f'Could not approve: the {vehicle_name} is already booked for some of those dates.',
        )
        return redirect('agencyrequests:inbox')

    notify_decision(booking, request)
    for declined_booking in Booking.objects.filter(pk__in=overlapping_ids).select_related('vehicle__agency', 'renter'):
        notify_decision(declined_booking, request)

    note = f' {auto_declined} overlapping request{"s were" if auto_declined != 1 else " was"} declined automatically.' if auto_declined else ''
    messages.success(request, f'Approved the request for the {vehicle_name}.{note}')
    return redirect('agencyrequests:inbox')


@login_required
@agency_required
@require_POST
def cancel_trip(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related('vehicle__agency', 'renter'),
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
    notify_cancelled_by_agency(booking, request)

    messages.success(
        request,
        f"Cancelled {_renter_name(booking.renter)}'s trip in the "
        f'{booking.vehicle.make} {booking.vehicle.model}. The dates are open again.',
    )
    return redirect('agencyrequests:inbox')
