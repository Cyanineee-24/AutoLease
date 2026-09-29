from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.db import models
from django.db.models import F, Func, Q


class DateRange(Func):
    """Wraps PostgreSQL daterange(start, end, bounds) for use in constraints."""
    function = 'daterange'
    output_field = DateRangeField()


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]

    renter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='bookings',
    )
    vehicle = models.ForeignKey(
        'fleet.Vehicle',
        on_delete=models.PROTECT,
        related_name='bookings',
    )
    start_date = models.DateField()
    end_date = models.DateField()
    daily_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    renter_message = models.TextField(blank=True)
    agency_response = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        default='pending',
        choices=STATUS_CHOICES,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F('start_date')),
                name='booking_end_after_start',
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        'pending', 'approved', 'declined',
                        'cancelled', 'completed',
                    ]
                ),
                name='booking_status_valid',
            ),
            ExclusionConstraint(
                name='booking_no_vehicle_overlap',
                expressions=[
                    ('vehicle', RangeOperators.EQUAL),
                    (
                        DateRange(
                            F('start_date'),
                            F('end_date'),
                            models.Value('[]'),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=Q(status='approved'),
            ),
        ]

    def __str__(self):
        return f'Booking #{self.pk} — {self.vehicle} ({self.start_date}–{self.end_date})'


class Review(models.Model):
    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name='review',
    )
    rating = models.SmallIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(rating__gte=1, rating__lte=5),
                name='review_rating_1_to_5',
            ),
        ]

    def __str__(self):
        return f'Review for Booking #{self.booking_id} ({self.rating}★)'
