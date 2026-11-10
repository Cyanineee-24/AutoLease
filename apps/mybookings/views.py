from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.bookings.models import Booking


@login_required
def my_bookings(request):
    bookings = list(
        Booking.objects.filter(renter=request.user)
        .select_related('vehicle__agency')
        .prefetch_related('vehicle__images')
        .order_by('-created_at')
    )
    for booking in bookings:
        booking.days = (booking.end_date - booking.start_date).days + 1
        booking.total = booking.daily_rate_snapshot * booking.days

    context = {
        'bookings': bookings,
        'pending_count': sum(1 for b in bookings if b.status == 'pending'),
    }
    return render(request, 'mybookings/my_bookings.html', context)


@login_required
@require_POST
def cancel_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk, renter=request.user)
    if booking.status != 'pending':
        messages.error(request, 'Only pending requests can be cancelled.')
        return redirect('mybookings:list')

    booking.status = 'cancelled'
    booking.save(update_fields=['status', 'updated_at'])
    messages.success(request, f'Request for the {booking.vehicle.make} {booking.vehicle.model} was cancelled.')
    return redirect('mybookings:list')
