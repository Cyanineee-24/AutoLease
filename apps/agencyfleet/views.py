from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import agency_required
from apps.fleet.models import Vehicle

from .forms import VehicleForm


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
