from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.decorators import agency_required
from apps.fleet.models import Vehicle


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
