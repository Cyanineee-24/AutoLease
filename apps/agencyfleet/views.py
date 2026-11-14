from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import agency_required
from apps.bookings.models import Booking
from apps.fleet.models import Vehicle

from .forms import VehicleForm

NO_LONGER_AVAILABLE_RESPONSE = 'This car is no longer available.'
STATUS_LABELS = dict(Vehicle.STATUS_CHOICES)


def _owned_vehicle(request, pk):
    """Another agency's car is a 404, never a 403 or redirect."""
    return get_object_or_404(Vehicle, pk=pk, agency__user=request.user)


def _vehicle_name(vehicle):
    return f'{vehicle.year} {vehicle.make} {vehicle.model}'


@login_required
@agency_required
def listings(request):
    today = timezone.localdate()
    vehicles = list(
        Vehicle.objects.filter(agency__user=request.user)
        .prefetch_related('images')
        .annotate(
            upcoming_count=Count(
                'bookings',
                filter=Q(bookings__status='approved', bookings__end_date__gte=today),
            ),
            pending_count=Count('bookings', filter=Q(bookings__status='pending')),
            booking_count=Count('bookings'),
        )
        .order_by('-created_at', '-pk')
    )
    context = {
        'vehicles': vehicles,
        'available_count': sum(1 for v in vehicles if v.status == 'available'),
        'status_choices': Vehicle.STATUS_CHOICES,
    }
    return render(request, 'agencyfleet/list.html', context)


@login_required
@agency_required
def create(request):
    if request.method == 'POST':
        form = VehicleForm(request.POST)
        if form.is_valid():
            vehicle = form.save(commit=False)
            vehicle.agency = request.user.agency_profile
            vehicle.save()
            messages.success(request, 'Car added.')
            return redirect('agencyfleet:list')
    else:
        form = VehicleForm()
    context = {'form': form, 'is_edit': False, 'page_title': 'Add a car'}
    return render(request, 'agencyfleet/form.html', context)


@login_required
@agency_required
def edit(request, pk):
    vehicle = _owned_vehicle(request, pk)
    # Built before binding: an invalid POST mutates form.instance.
    page_title = f'Edit {vehicle} details'
    if request.method == 'POST':
        form = VehicleForm(request.POST, instance=vehicle)
        if form.is_valid():
            # Existing bookings keep their daily_rate_snapshot.
            form.save()
            messages.success(request, 'Changes saved.')
            return redirect('agencyfleet:list')
    else:
        form = VehicleForm(instance=vehicle)
    context = {'form': form, 'is_edit': True, 'page_title': page_title}
    return render(request, 'agencyfleet/form.html', context)


@login_required
@agency_required
@require_POST
def change_status(request, pk):
    vehicle = _owned_vehicle(request, pk)
    new_status = request.POST.get('status', '')
    if new_status not in STATUS_LABELS:
        messages.error(request, 'Choose Available, Unavailable or Maintenance.')
        return redirect('agencyfleet:list')

    name = _vehicle_name(vehicle)
    label = STATUS_LABELS[new_status]
    if new_status == vehicle.status:
        messages.info(request, f'The {name} is already set to {label}.')
        return redirect('agencyfleet:list')

    if new_status == 'available':
        vehicle.status = new_status
        vehicle.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'The {name} is now {label}.')
        return redirect('agencyfleet:list')

    # Decision D4: a car with an approved trip that is upcoming or in progress
    # can't be taken off the road until that trip is cancelled.
    today = timezone.localdate()
    upcoming = Booking.objects.filter(vehicle=vehicle, status='approved', end_date__gte=today).count()
    if upcoming:
        messages.error(
            request,
            f'This car has {upcoming} upcoming trip{"s" if upcoming != 1 else ""}. '
            f'Cancel {"them" if upcoming != 1 else "it"} before changing its status.',
        )
        return redirect('agencyfleet:list')

    now = timezone.now()
    with transaction.atomic():
        vehicle.status = new_status
        vehicle.save(update_fields=['status', 'updated_at'])
        declined = Booking.objects.filter(
            vehicle=vehicle,
            status='pending',
            end_date__gte=today,
        ).update(
            status='declined',
            agency_response=NO_LONGER_AVAILABLE_RESPONSE,
            decided_at=now,
            updated_at=now,
        )

    note = f' {declined} pending request{"s were" if declined != 1 else " was"} declined.' if declined else ''
    messages.success(request, f'The {name} is now {label}.{note}')
    return redirect('agencyfleet:list')


@login_required
@agency_required
@require_POST
def delete(request, pk):
    vehicle = _owned_vehicle(request, pk)
    if vehicle.bookings.exists():
        messages.error(request, "Cars with booking history can't be deleted. Set it to Unavailable instead.")
        return redirect('agencyfleet:list')

    images = list(vehicle.images.all())
    # Row first (Favorite and VehicleImage rows cascade), files second, so a
    # failed delete never leaves a car pointing at missing files.
    vehicle.delete()
    for image in images:
        image.image.delete(save=False)
    messages.success(request, 'Car deleted.')
    return redirect('agencyfleet:list')
