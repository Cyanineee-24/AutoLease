from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.bookings.lifecycle import agency_cancel_reason, can_cancel, display_status
from apps.bookings.models import Booking, Review

from .forms import ReviewForm


def _is_reviewable(booking, today):
    """Approved trips that have ended and have no review yet."""
    return (
        booking.status == 'approved'
        and booking.end_date < today
        and not Review.objects.filter(booking=booking).exists()
    )


@login_required
def my_bookings(request):
    bookings = list(
        Booking.objects.filter(renter=request.user)
        .select_related('vehicle__agency', 'review')
        .prefetch_related('vehicle__images')
        .order_by('-created_at')
    )
    today = timezone.localdate()
    for booking in bookings:
        booking.days = (booking.end_date - booking.start_date).days + 1
        booking.total = booking.daily_rate_snapshot * booking.days
        booking.status_key, booking.status_label = display_status(booking, today)
        booking.can_cancel = can_cancel(booking, today)
        booking.agency_reason = agency_cancel_reason(booking)
        try:
            booking.my_review = booking.review
        except Review.DoesNotExist:
            booking.my_review = None
        booking.can_review = (
            booking.my_review is None
            and booking.status == 'approved'
            and booking.end_date < today
        )

    context = {
        'bookings': bookings,
        'pending_count': sum(1 for b in bookings if b.status == 'pending'),
    }
    return render(request, 'mybookings/my_bookings.html', context)


@login_required
@require_POST
def cancel_booking(request, pk):
    booking = get_object_or_404(Booking.objects.select_related('vehicle'), pk=pk, renter=request.user)
    if not can_cancel(booking, timezone.localdate()):
        if booking.status == 'approved':
            messages.error(request, "This trip has already started, so it can't be cancelled.")
        else:
            messages.error(request, 'Only pending requests and upcoming trips can be cancelled.')
        return redirect('mybookings:list')

    was_approved = booking.status == 'approved'
    # The no-overlap constraint only covers approved bookings, so this frees the dates.
    booking.status = 'cancelled'
    booking.save(update_fields=['status', 'updated_at'])

    vehicle_name = f'{booking.vehicle.make} {booking.vehicle.model}'
    if was_approved:
        start = booking.start_date
        messages.success(
            request,
            f'Your trip in the {vehicle_name} on {start:%b} {start.day} was cancelled. The dates are open again.',
        )
    else:
        messages.success(request, f'Request for the {vehicle_name} was cancelled.')
    return redirect('mybookings:list')


@login_required
def review_booking(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related('vehicle'), pk=pk, renter=request.user
    )
    if not _is_reviewable(booking, timezone.localdate()):
        messages.error(request, 'You can review a trip once, after it has ended.')
        return redirect('mybookings:list')

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.booking = booking
            try:
                with transaction.atomic():
                    review.save()
                    booking.status = 'completed'
                    booking.save(update_fields=['status', 'updated_at'])
            except IntegrityError:
                messages.error(request, 'This trip has already been reviewed.')
                return redirect('mybookings:list')
            messages.success(request, 'Thanks! Your review is now on the car page.')
            return redirect('mybookings:list')
    else:
        form = ReviewForm()

    context = {
        'booking': booking,
        'form': form,
        'days': (booking.end_date - booking.start_date).days + 1,
    }
    return render(request, 'mybookings/review_form.html', context)
