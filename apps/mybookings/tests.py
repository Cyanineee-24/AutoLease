import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
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


class CancelBookingTests(BookingStatusTestBase):
    def setUp(self):
        self.client.force_login(self.renter_user)
        self.today = timezone.localdate()

    def cancel(self, booking):
        return self.client.post(reverse('mybookings:cancel', args=[booking.pk]))

    def messages_text(self, response):
        return ' '.join(str(m) for m in get_messages(response.wsgi_request))

    def test_pending_can_be_cancelled(self):
        pending = self.make_trip('PEN 0101', 'Innova', self.today, 3, 4, status='pending')
        response = self.cancel(pending)
        self.assertRedirects(response, reverse('mybookings:list'), fetch_redirect_response=False)
        self.assertIn('Request for the Toyota Innova was cancelled.', self.messages_text(response))
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'cancelled')

    def test_approved_starting_tomorrow_can_be_cancelled_and_frees_dates(self):
        trip = self.make_trip('TMR 0102', 'Fortuner', self.today, 1, 3)
        Booking.objects.filter(pk=trip.pk).update(agency_response='See you at the airport.')

        response = self.cancel(trip)
        start = trip.start_date
        self.assertIn(
            f'Your trip in the Toyota Fortuner on {start:%b} {start.day} was cancelled. The dates are open again.',
            self.messages_text(response),
        )
        trip.refresh_from_db()
        self.assertEqual(trip.status, 'cancelled')
        self.assertEqual(trip.agency_response, 'See you at the airport.')

        # Another renter can now be approved for the very same dates.
        other_renter = User.objects.create_user(
            username='other@example.com', email='other@example.com', password='password123', is_renter=True,
        )
        rival = Booking.objects.create(
            vehicle=trip.vehicle,
            renter=other_renter,
            start_date=trip.start_date,
            end_date=trip.end_date,
            daily_rate_snapshot=trip.daily_rate_snapshot,
        )
        self.client.force_login(self.agency_user)
        self.client.post(reverse('agencyrequests:decide', args=[rival.pk]), {'action': 'approve'})
        rival.refresh_from_db()
        self.assertEqual(rival.status, 'approved')

    def test_approved_starting_today_refused(self):
        trip = self.make_trip('TOD 0103', 'Hilux', self.today, 0, 2)
        response = self.cancel(trip)
        self.assertIn("This trip has already started, so it can't be cancelled.", self.messages_text(response))
        trip.refresh_from_db()
        self.assertEqual(trip.status, 'approved')

    def test_other_states_refused(self):
        cases = [
            (self.past_trip, 'approved', "This trip has already started, so it can't be cancelled."),
            (self.make_trip('DEC 0104', 'Jimny', self.today, 3, 4, status='declined'), 'declined',
             'Only pending requests and upcoming trips can be cancelled.'),
            (self.make_trip('CAN 0105', 'Navara', self.today, 3, 4, status='cancelled'), 'cancelled',
             'Only pending requests and upcoming trips can be cancelled.'),
            (self.make_trip('CMP 0106', 'Stargazer', self.today, -6, -5, status='completed'), 'completed',
             'Only pending requests and upcoming trips can be cancelled.'),
        ]
        for booking, status, message in cases:
            with self.subTest(status=status, pk=booking.pk):
                response = self.cancel(booking)
                self.assertIn(message, self.messages_text(response))
                booking.refresh_from_db()
                self.assertEqual(booking.status, status)

    def test_other_renters_booking_404(self):
        other_renter = User.objects.create_user(
            username='other@example.com', email='other@example.com', password='password123', is_renter=True,
        )
        self.client.force_login(other_renter)
        response = self.cancel(self.future_trip)
        self.assertEqual(response.status_code, 404)
        self.future_trip.refresh_from_db()
        self.assertEqual(self.future_trip.status, 'approved')

    def test_get_not_allowed(self):
        response = self.client.get(reverse('mybookings:cancel', args=[self.future_trip.pk]))
        self.assertEqual(response.status_code, 405)

    def test_cancel_trip_button_only_for_upcoming(self):
        response = self.client.get(reverse('mybookings:list'))
        self.assertContains(response, reverse('mybookings:cancel', args=[self.future_trip.pk]))
        # Count the button itself; the form's data-confirm-action label also says "Cancel trip".
        self.assertContains(response, '>Cancel trip</button>', count=1)
        self.assertContains(
            response,
            'data-confirm="Cancel this trip? The agency will be told and the dates will open up for others."',
        )
        self.assertNotContains(response, reverse('mybookings:cancel', args=[self.current_trip.pk]))
        self.assertNotContains(response, reverse('mybookings:cancel', args=[self.past_trip.pk]))

    def test_agency_cancel_reason_shown_without_prefix(self):
        Booking.objects.filter(pk=self.future_trip.pk).update(
            status='cancelled',
            agency_response='Cancelled by the agency: The car failed inspection.',
        )
        response = self.client.get(reverse('mybookings:list'))
        self.assertContains(response, "Agency's reason:")
        self.assertContains(response, 'The car failed inspection.')
        self.assertNotContains(response, 'Cancelled by the agency: ')
        self.assertContains(response, '<span class="status-badge status-badge--cancelled">Cancelled by agency</span>', html=True)


def messages_text(response):
    return ' '.join(str(m) for m in get_messages(response.wsgi_request))


class ReviewTests(BookingStatusTestBase):
    REFUSED = 'You can review a trip once, after it has ended.'

    def setUp(self):
        self.today = timezone.localdate()
        self.client.force_login(self.renter_user)
        self.ended_yesterday = self.make_trip('END 2001', 'Fortuner', self.today, -3, -1)

    def review_url(self, booking):
        return reverse('mybookings:review', args=[booking.pk])

    def post_review(self, booking, **data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.review_url(booking), data)

    def test_review_finished_trip(self):
        page = self.client.get(self.review_url(self.ended_yesterday))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="rating"')
        self.assertContains(page, 'name="comment"')

        response = self.post_review(self.ended_yesterday, rating='5', comment='Spotless car, easy pick-up.')
        self.assertRedirects(response, reverse('mybookings:list'), fetch_redirect_response=False)
        self.assertIn('Thanks! Your review is now on the car page.', messages_text(response))
        review = Review.objects.get(booking=self.ended_yesterday)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, 'Spotless car, easy pick-up.')
        self.ended_yesterday.refresh_from_db()
        self.assertEqual(self.ended_yesterday.status, 'completed')

    def test_second_review_refused(self):
        self.post_review(self.ended_yesterday, rating='5')
        for response in (
            self.client.get(self.review_url(self.ended_yesterday)),
            self.post_review(self.ended_yesterday, rating='1', comment='Changed my mind'),
        ):
            self.assertRedirects(response, reverse('mybookings:list'), fetch_redirect_response=False)
            self.assertIn(self.REFUSED, messages_text(response))
        self.assertEqual(Review.objects.filter(booking=self.ended_yesterday).count(), 1)
        self.assertEqual(Review.objects.get(booking=self.ended_yesterday).rating, 5)

    def test_unfinished_or_non_approved_trips_refused(self):
        cases = [
            self.make_trip('TOD 2002', 'Hilux', self.today, -2, 0),                       # ends today
            self.future_trip,                                                             # future
            self.current_trip,                                                            # in progress
            self.make_trip('PEN 2003', 'Jimny', self.today, -5, -3, status='pending'),
            self.make_trip('DEC 2004', 'Navara', self.today, -5, -3, status='declined'),
            self.make_trip('CAN 2005', 'Stargazer', self.today, -5, -3, status='cancelled'),
        ]
        for booking in cases:
            with self.subTest(status=booking.status, end=booking.end_date):
                for response in (
                    self.client.get(self.review_url(booking)),
                    self.post_review(booking, rating='5'),
                ):
                    self.assertRedirects(response, reverse('mybookings:list'), fetch_redirect_response=False)
                    self.assertIn(self.REFUSED, messages_text(response))
                self.assertFalse(Review.objects.filter(booking=booking).exists())

    def test_invalid_rating_or_long_comment_rejected(self):
        cases = [
            ({}, 'Pick a star rating.'),
            ({'rating': '0'}, 'Select a valid choice.'),
            ({'rating': '6'}, 'Select a valid choice.'),
            ({'rating': '5', 'comment': 'x' * 1001}, 'Ensure this value has at most 1000 characters'),
        ]
        for data, error in cases:
            with self.subTest(data=data.get('rating'), comment_len=len(data.get('comment', ''))):
                response = self.post_review(self.ended_yesterday, **data)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, error)
                self.assertFalse(Review.objects.filter(booking=self.ended_yesterday).exists())
                self.ended_yesterday.refresh_from_db()
                self.assertEqual(self.ended_yesterday.status, 'approved')

    def test_other_renters_booking_404(self):
        other = User.objects.create_user(
            username='other@example.com', email='other@example.com', password='password123', is_renter=True,
        )
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.review_url(self.ended_yesterday)).status_code, 404)
        self.assertEqual(self.post_review(self.ended_yesterday, rating='5').status_code, 404)
        self.assertFalse(Review.objects.filter(booking=self.ended_yesterday).exists())

    def test_review_appears_on_car_page_and_dashboard_card(self):
        self.post_review(self.ended_yesterday, rating='5', comment='Would rent again.')
        vehicle = self.ended_yesterday.vehicle
        self.client.logout()

        detail = self.client.get(reverse('fleet:vehicle_detail', args=[vehicle.pk]))
        self.assertContains(detail, 'Would rent again.')
        self.assertContains(detail, '<span class="review-author">Juan</span>', html=True)
        self.assertNotContains(detail, 'renter@example.com')

        dashboard = self.client.get(reverse('home:dashboard'))
        card = next(v for v in dashboard.context['page_obj'] if v.pk == vehicle.pk)
        self.assertEqual(card.review_count, 1)
        self.assertEqual(card.avg_rating, 5)
        self.assertContains(dashboard, '<span>5.0</span>', html=True)


class MyBookingsListTests(BookingStatusTestBase):
    def test_guest_redirected_to_login(self):
        url = reverse('mybookings:list')
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('login:login')}?next={url}", fetch_redirect_response=False)

    def test_only_own_bookings_newest_first(self):
        other = User.objects.create_user(
            username='other@example.com', email='other@example.com', password='password123', is_renter=True,
        )
        others_trip = self.make_trip('OTH 3001', 'Innova', timezone.localdate(), 3, 4)
        Booking.objects.filter(pk=others_trip.pk).update(renter=other)

        now = timezone.now()
        for hours_ago, booking in ((3, self.future_trip), (2, self.current_trip), (1, self.past_trip)):
            Booking.objects.filter(pk=booking.pk).update(created_at=now - datetime.timedelta(hours=hours_ago))

        self.client.force_login(self.renter_user)
        response = self.client.get(reverse('mybookings:list'))
        self.assertEqual(
            [b.pk for b in response.context['bookings']],
            [self.past_trip.pk, self.current_trip.pk, self.future_trip.pk],
        )
        self.assertNotContains(response, 'Toyota Innova')
        self.assertContains(response, '3 requests')

    def test_empty_state(self):
        empty = User.objects.create_user(
            username='new@example.com', email='new@example.com', password='password123', is_renter=True,
        )
        self.client.force_login(empty)
        response = self.client.get(reverse('mybookings:list'))
        self.assertContains(response, 'No trips booked... yet')
        self.assertContains(response, f'<a class="button" href="{reverse("home:dashboard")}">Browse cars</a>', html=True)
        self.assertEqual(list(response.context['bookings']), [])
