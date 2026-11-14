from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import agency_required
from apps.bookings.models import Booking
from apps.fleet.models import Vehicle, VehicleImage

from .forms import MAX_PHOTOS_PER_CAR, VehicleForm, VehiclePhotoForm

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
            messages.success(request, 'Car added. Add photos so renters can see it.')
            return redirect('agencyfleet:photos', pk=vehicle.pk)
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


def _owned_image(vehicle, image_pk):
    return get_object_or_404(VehicleImage, pk=image_pk, vehicle=vehicle)


@login_required
@agency_required
def photos(request, pk):
    vehicle = _owned_vehicle(request, pk)
    form = VehiclePhotoForm()

    if request.method == 'POST':
        if vehicle.images.count() >= MAX_PHOTOS_PER_CAR:
            messages.error(request, f'A car can have up to {MAX_PHOTOS_PER_CAR} photos. Delete one to add another.')
            return redirect('agencyfleet:photos', pk=vehicle.pk)
        form = VehiclePhotoForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                current = vehicle.images.aggregate(max_order=Max('sort_order'))['max_order']
                VehicleImage.objects.create(
                    vehicle=vehicle,
                    image=form.cleaned_data['image'],
                    sort_order=0 if current is None else current + 1,
                    is_primary=not vehicle.images.filter(is_primary=True).exists(),
                )
            messages.success(request, 'Photo added.')
            return redirect('agencyfleet:photos', pk=vehicle.pk)

    images = vehicle.gallery_images
    context = {
        'vehicle': vehicle,
        'images': images,
        # The photo renters see first (gallery order), even if none is flagged.
        'main_image_id': images[0].pk if images else None,
        'form': form,
        'can_upload': len(images) < MAX_PHOTOS_PER_CAR,
        'max_photos': MAX_PHOTOS_PER_CAR,
    }
    return render(request, 'agencyfleet/photos.html', context)


@login_required
@agency_required
@require_POST
def photo_primary(request, pk, image_pk):
    vehicle = _owned_vehicle(request, pk)
    image = _owned_image(vehicle, image_pk)
    with transaction.atomic():
        vehicle.images.update(is_primary=False)
        VehicleImage.objects.filter(pk=image.pk).update(is_primary=True)
    messages.success(request, 'Main photo updated.')
    return redirect('agencyfleet:photos', pk=vehicle.pk)


@login_required
@agency_required
@require_POST
def photo_delete(request, pk, image_pk):
    vehicle = _owned_vehicle(request, pk)
    image = _owned_image(vehicle, image_pk)
    with transaction.atomic():
        image.delete()
        if image.is_primary:
            successor = vehicle.images.order_by('sort_order', 'id').first()
            if successor:
                successor.is_primary = True
                successor.save(update_fields=['is_primary'])
    image.image.delete(save=False)
    messages.success(request, 'Photo deleted.')
    return redirect('agencyfleet:photos', pk=vehicle.pk)
