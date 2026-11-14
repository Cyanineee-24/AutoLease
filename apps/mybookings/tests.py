import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AgencyProfile
from apps.bookings.models import Booking, Review
from apps.fleet.models import Vehicle

User = get_user_model()


class BookingStatusTestBase(TestCase):
    """Shared data: one agency, one renter, three cars (one per trip phase)."""

    @classmethod
    def setUpTestData(cls):
        cls.agency_user = User.objects.create_user(
            username='agency@example.com',
            email='agency@example.com',
            password='password123',
            is_agency=True,
            first_name='Agency',
        )
        cls.agency_profile = AgencyProfile.objects.create(
            user=cls.agency_user,
            business_name='Cebu City Wheels',
            contact_number='0917 111 2222',
        )
        cls.renter_user = User.objects.create_user(
            username='renter@example.com',
            email='renter@example.com',
            password='password123',
            is_renter=True,
            first_name='Juan',
        )
        today = timezone.localdate()
        cls.future_trip = cls.make_trip('FUT 0001', 'Vios', today, 5, 7)
        cls.current_trip = cls.make_trip('CUR 0002', 'City', today, -1, 1)
        cls.past_trip = cls.make_trip('PST 0003', 'Almera', today, -9, -7)

    @classmethod
    def make_trip(cls, plate, model, today, start_offset, end_offset, status='approved'):
        vehicle = Vehicle.objects.create(
            agency=cls.agency_profile,
            make='Toyota',
            model=model,
            year=2022,
            plate_number=plate,
            transmission='Automatic',
            fuel_type='Gasoline',
            seats=5,
            color='White',
            daily_rate=Decimal('2500.00'),
            city='Cebu City',
        )
        return Booking.objects.create(
            vehicle=vehicle,
            renter=cls.renter_user,
            start_date=today + datetime.timedelta(days=start_offset),
            end_date=today + datetime.timedelta(days=end_offset),
            daily_rate_snapshot=vehicle.daily_rate,
            status=status,
        )


class MyBookingsStatusLabelTests(BookingStatusTestBase):
    def setUp(self):
        self.client.force_login(self.renter_user)

    def get_page(self):
        return self.client.get(reverse('mybookings:list'))

    def test_approved_trips_show_date_based_labels(self):
        response = self.get_page()
        self.assertContains(response, '<span class="status-badge status-badge--upcoming">Upcoming</span>', html=True)
        self.assertContains(response, '<span class="status-badge status-badge--in_progress">In progress</span>', html=True)
        self.assertContains(response, '<span class="status-badge status-badge--completed">Completed</span>', html=True)
        self.assertNotContains(response, 'status-badge--approved')
        self.assertNotContains(response, '>Approved<')

    def test_finished_trip_without_review_still_offers_review(self):
        response = self.get_page()
        self.assertContains(response, reverse('mybookings:review', args=[self.past_trip.pk]))
        self.assertContains(response, 'Leave a review', count=1)
        self.assertNotContains(response, reverse('mybookings:review', args=[self.future_trip.pk]))
        self.assertNotContains(response, reverse('mybookings:review', args=[self.current_trip.pk]))

    def test_reviewed_trip_shows_completed_and_rating(self):
        Review.objects.create(booking=self.past_trip, rating=4, comment='Nice')
        Booking.objects.filter(pk=self.past_trip.pk).update(status='completed')
        response = self.get_page()
        self.assertContains(response, '<span class="status-badge status-badge--completed">Completed</span>', html=True)
        self.assertContains(response, 'You rated 4')
        self.assertNotContains(response, 'Leave a review')

    def test_pending_cancel_unchanged(self):
        pending = self.make_trip('PEN 0004', 'Innova', timezone.localdate(), 3, 4, status='pending')
        response = self.get_page()
        self.assertContains(response, '<span class="status-badge status-badge--pending">Pending</span>', html=True)
        self.assertContains(response, reverse('mybookings:cancel', args=[pending.pk]))
