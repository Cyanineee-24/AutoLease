from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.bookings.models import Review
from apps.fleet.forms import VehicleSearchForm
from apps.fleet.models import Favorite, Vehicle
from apps.userprofile.models import DriverLicense
from apps.usersettings.models import UserSettings


@login_required
@require_POST
def favorite_toggle(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk, status='available')

    favorite = Favorite.objects.filter(user=request.user, vehicle=vehicle)
    if favorite.exists():
        favorite.delete()
        favorited = False
    else:
        Favorite.objects.create(user=request.user, vehicle=vehicle)
        favorited = True

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'favorited': favorited})

    next_url = request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        return redirect(next_url)

    return redirect('fleet:vehicle_detail', pk=vehicle.pk)


@login_required
def vehicle_detail(request, pk):
    vehicle = get_object_or_404(
        Vehicle.objects.available()
        .for_listing(request.user)
        .select_related('agency__user'),
        pk=pk,
    )

    form = VehicleSearchForm(request.GET)
    form.is_valid()
    search_qs = form.querystring()
    back_url = reverse('home:dashboard') + (f'?{search_qs}' if search_qs else '')

    start_date = ''
    end_date = ''
    if form.cleaned_data.get('start_date') and form.cleaned_data.get('end_date'):
        start_date = form.cleaned_data['start_date'].isoformat()
        end_date = form.cleaned_data['end_date'].isoformat()

    business_name = (vehicle.agency.business_name or '').strip()
    words = business_name.split()
    host_initials = ''.join(w[0] for w in words[:2]).upper() if words else ''

    setting_val = (
        UserSettings.objects.filter(user=vehicle.agency.user)
        .values_list('show_contact_number', flat=True)
        .first()
    )
    show_contact = True if setting_val is None else bool(setting_val)
    contact_number = vehicle.agency.contact_number or ''

    reviews = list(
        Review.objects.filter(booking__vehicle=vehicle)
        .select_related('booking__renter')
        .order_by('-created_at')[:6]
    )
    for review in reviews:
        renter_first = (review.booking.renter.first_name or '').strip()
        review.reviewer_display_name = renter_first if renter_first else 'Renter'

    is_owner = vehicle.agency.user_id == request.user.pk
    has_license = DriverLicense.objects.filter(user=request.user).exists()

    context = {
        'vehicle': vehicle,
        'is_owner': is_owner,
        'has_license': has_license,
        'today': timezone.localdate(),
        'host_initials': host_initials,
        'show_contact': show_contact,
        'contact_number': contact_number,
        'reviews': reviews,
        'daily_rate': vehicle.daily_rate,
        'back_url': back_url,
        'search_qs': search_qs,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'fleet/vehicle_detail.html', context)
