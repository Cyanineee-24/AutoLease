import datetime

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AgencyProfile
from apps.bookings.lifecycle import AGENCY_CANCEL_PREFIX
from apps.bookings.models import Booking
from apps.mybookings.tests import BookingStatusTestBase

User = get_user_model()


def messages_text(response):
    return ' '.join(str(m) for m in get_messages(response.wsgi_request))


class InboxHistoryStatusLabelTests(BookingStatusTestBase):
    def test_history_shows_date_based_labels(self):
        self.client.force_login(self.agency_user)
        response = self.client.get(reverse('agencyrequests:inbox'))
        self.assertEqual(response.status_code, 200)
        rows = response.context['active'] + response.context['history']
        self.assertEqual(
            {b.pk: (b.status_key, b.status_label) for b in rows},
            {
                self.future_trip.pk: ('upcoming', 'Upcoming'),
                self.current_trip.pk: ('in_progress', 'In progress'),
                self.past_trip.pk: ('completed', 'Completed'),
            },
        )
        self.assertContains(response, '<span class="status-badge status-badge--upcoming">Upcoming</span>', html=True)
        self.assertContains(response, '<span class="status-badge status-badge--in_progress">In progress</span>', html=True)
        self.assertContains(response, '<span class="status-badge status-badge--completed">Completed</span>', html=True)
        self.assertNotContains(response, 'status-badge--approved')

    def test_declined_and_cancelled_rows_keep_their_labels(self):
        today = self.future_trip.start_date
        self.make_trip('DEC 0005', 'Hilux', today, 1, 2, status='declined')
        self.make_trip('CAN 0006', 'Jimny', today, 1, 2, status='cancelled')
        self.client.force_login(self.agency_user)
        response = self.client.get(reverse('agencyrequests:inbox'))
        self.assertContains(response, '<span class="status-badge status-badge--declined">Declined</span>', html=True)
        self.assertContains(response, '<span class="status-badge status-badge--cancelled">Cancelled</span>', html=True)


class InboxSectionsTests(BookingStatusTestBase):
    def setUp(self):
        self.client.force_login(self.agency_user)
        self.today = timezone.localdate()

    def test_inbox_splits_pending_upcoming_and_history(self):
        pending = self.make_trip('PEN 0201', 'Innova', self.today, 3, 4, status='pending')
        declined = self.make_trip('DEC 0202', 'Hilux', self.today, 3, 4, status='declined')
        response = self.client.get(reverse('agencyrequests:inbox'))

        self.assertEqual([b.pk for b in response.context['pending']], [pending.pk])
        # Ordered by start_date: the in-progress trip first, then the upcoming one.
        self.assertEqual([b.pk for b in response.context['active']], [self.current_trip.pk, self.future_trip.pk])
        self.assertEqual({b.pk for b in response.context['history']}, {self.past_trip.pk, declined.pk})
        self.assertContains(response, '1 awaiting your decision · 2 upcoming trips')
        self.assertContains(response, '<h2 class="inbox-section-title">Upcoming trips</h2>', html=True)

    def test_only_upcoming_trip_has_cancel_form(self):
        response = self.client.get(reverse('agencyrequests:inbox'))
        self.assertContains(response, reverse('agencyrequests:cancel', args=[self.future_trip.pk]))
        self.assertNotContains(response, reverse('agencyrequests:cancel', args=[self.current_trip.pk]))
        self.assertContains(response, "Trip in progress. It can't be cancelled.")
        self.assertContains(response, 'Reason for cancelling (the renter will see this)')
        self.assertContains(response, 'data-confirm="Cancel this trip? The renter will see your reason."')
        self.assertContains(response, 'js/agencyrequests/agencyrequests.js')

    def test_section_hidden_when_no_active_trips(self):
        Booking.objects.filter(pk__in=[self.future_trip.pk, self.current_trip.pk]).update(status='declined')
        response = self.client.get(reverse('agencyrequests:inbox'))
        self.assertNotContains(response, '<h2 class="inbox-section-title">Upcoming trips</h2>', html=True)
        self.assertContains(response, '0 awaiting your decision · 0 upcoming trips')


class AgencyCancelTripTests(BookingStatusTestBase):
    REASON = 'The car failed its safety inspection.'

    def setUp(self):
        self.client.force_login(self.agency_user)
        self.today = timezone.localdate()

    def cancel(self, booking, reason=REASON):
        return self.client.post(reverse('agencyrequests:cancel', args=[booking.pk]), {'reason': reason})

    def test_cancel_upcoming_trip_with_reason(self):
        decided_at = timezone.now() - datetime.timedelta(days=2)
        Booking.objects.filter(pk=self.future_trip.pk).update(decided_at=decided_at)

        response = self.cancel(self.future_trip, reason=f'  {self.REASON}  ')
        self.assertRedirects(response, reverse('agencyrequests:inbox'), fetch_redirect_response=False)
        self.assertIn(
            "Cancelled Juan's trip in the Toyota Vios. The dates are open again.",
            messages_text(response),
        )
        self.future_trip.refresh_from_db()
        self.assertEqual(self.future_trip.status, 'cancelled')
        self.assertEqual(self.future_trip.agency_response, f'{AGENCY_CANCEL_PREFIX}{self.REASON}')
        self.assertEqual(self.future_trip.decided_at, decided_at)

        # The renter sees who cancelled and why.
        self.client.force_login(self.renter_user)
        page = self.client.get(reverse('mybookings:list'))
        self.assertContains(page, '<span class="status-badge status-badge--cancelled">Cancelled by agency</span>', html=True)
        self.assertContains(page, "Agency's reason:")
        self.assertContains(page, self.REASON)

        # The agency's history shows the same label.
        self.client.force_login(self.agency_user)
        inbox = self.client.get(reverse('agencyrequests:inbox'))
        self.assertIn(self.future_trip.pk, [b.pk for b in inbox.context['history']])
        self.assertContains(inbox, '<span class="status-badge status-badge--cancelled">Cancelled by agency</span>', html=True)

    def test_empty_reason_refused(self):
        for reason in ('', '    '):
            with self.subTest(reason=repr(reason)):
                response = self.cancel(self.future_trip, reason=reason)
                self.assertIn("Tell the renter why you're cancelling.", messages_text(response))
                self.future_trip.refresh_from_db()
                self.assertEqual(self.future_trip.status, 'approved')
                self.assertEqual(self.future_trip.agency_response, '')

    def test_started_or_finished_trips_refused(self):
        starts_today = self.make_trip('TOD 0203', 'Fortuner', self.today, 0, 2)
        for booking in (starts_today, self.current_trip, self.past_trip):
            with self.subTest(pk=booking.pk):
                response = self.cancel(booking)
                self.assertIn("This trip has already started, so it can't be cancelled.", messages_text(response))
                booking.refresh_from_db()
                self.assertEqual(booking.status, 'approved')

    def test_non_approved_bookings_refused(self):
        for plate, status in (
            ('PEN 0301', 'pending'),
            ('DEC 0302', 'declined'),
            ('CAN 0303', 'cancelled'),
            ('CMP 0304', 'completed'),
        ):
            with self.subTest(status=status):
                booking = self.make_trip(plate, 'Navara', self.today, 3, 4, status=status)
                response = self.cancel(booking)
                self.assertIn('Only upcoming trips can be cancelled.', messages_text(response))
                booking.refresh_from_db()
                self.assertEqual(booking.status, status)

    def test_other_agency_booking_404(self):
        other_agency = User.objects.create_user(
            username='rival@example.com', email='rival@example.com', password='password123', is_agency=True,
        )
        AgencyProfile.objects.create(user=other_agency, business_name='Rival Rentals', contact_number='0917 999 0000')
        self.client.force_login(other_agency)
        self.assertEqual(self.cancel(self.future_trip).status_code, 404)
        self.future_trip.refresh_from_db()
        self.assertEqual(self.future_trip.status, 'approved')

    def test_renter_blocked_by_agency_required(self):
        self.client.force_login(self.renter_user)
        response = self.cancel(self.future_trip)
        self.assertRedirects(response, reverse('home:dashboard'), fetch_redirect_response=False)
        self.assertIn('Only rental agencies', messages_text(response))
        self.future_trip.refresh_from_db()
        self.assertEqual(self.future_trip.status, 'approved')

    def test_get_not_allowed(self):
        response = self.client.get(reverse('agencyrequests:cancel', args=[self.future_trip.pk]))
        self.assertEqual(response.status_code, 405)

    def test_after_cancelling_car_can_go_to_maintenance(self):
        vehicle = self.future_trip.vehicle
        status_url = reverse('agencyfleet:status', args=[vehicle.pk])

        self.client.post(status_url, {'status': 'maintenance'})
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.status, 'available')  # blocked by the upcoming trip

        self.cancel(self.future_trip)
        self.client.post(status_url, {'status': 'maintenance'})
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.status, 'maintenance')
