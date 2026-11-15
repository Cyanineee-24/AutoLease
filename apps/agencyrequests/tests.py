import datetime

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AgencyProfile
from apps.bookings.lifecycle import AGENCY_CANCEL_PREFIX
from apps.bookings.models import Booking
from apps.mybookings.tests import BookingStatusTestBase
from apps.usersettings.models import UserSettings

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


class DecideRulesTests(BookingStatusTestBase):
    """Approve / decline rules of agencyrequests:decide (the original booking flow)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.other_renter = User.objects.create_user(
            username='paolo@example.com', email='paolo@example.com', password='password123',
            is_renter=True, first_name='Paolo',
        )
        cls.third_renter = User.objects.create_user(
            username='ana@example.com', email='ana@example.com', password='password123',
            is_renter=True, first_name='Ana',
        )

    def setUp(self):
        self.today = timezone.localdate()
        self.client.force_login(self.agency_user)
        # A car with no approved trips, so approvals are possible.
        self.car = self.make_trip('DEC 1000', 'Innova', self.today, 30, 31, status='declined').vehicle

    def pending(self, renter, start_offset, end_offset, vehicle=None, status='pending'):
        return Booking.objects.create(
            vehicle=vehicle or self.car,
            renter=renter,
            start_date=self.today + datetime.timedelta(days=start_offset),
            end_date=self.today + datetime.timedelta(days=end_offset),
            daily_rate_snapshot=(vehicle or self.car).daily_rate,
            status=status,
        )

    def decide(self, booking, **data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('agencyrequests:decide', args=[booking.pk]), data)

    def test_approve(self):
        booking = self.pending(self.renter_user, 5, 7)
        response = self.decide(booking, action='approve', agency_response='Pick-up at 9 AM.')
        self.assertRedirects(response, reverse('agencyrequests:inbox'), fetch_redirect_response=False)
        self.assertIn('Approved the request for the Toyota Innova.', messages_text(response))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'approved')
        self.assertEqual(booking.agency_response, 'Pick-up at 9 AM.')
        self.assertIsNotNone(booking.decided_at)

    def test_decline_with_and_without_reply(self):
        for reply in ('Fully booked that week.', ''):
            with self.subTest(reply=reply):
                booking = self.pending(self.renter_user, 5, 7)
                response = self.decide(booking, action='decline', agency_response=reply)
                self.assertRedirects(response, reverse('agencyrequests:inbox'), fetch_redirect_response=False)
                self.assertIn('Declined the request for the Toyota Innova.', messages_text(response))
                booking.refresh_from_db()
                self.assertEqual(booking.status, 'declined')
                self.assertEqual(booking.agency_response, reply)
                self.assertIsNotNone(booking.decided_at)

    def test_approve_auto_declines_overlapping_pending_requests(self):
        chosen = self.pending(self.renter_user, 5, 7)
        touches_start = self.pending(self.other_renter, 2, 5)    # ends on chosen's first day
        touches_end = self.pending(self.third_renter, 7, 9)      # starts on chosen's last day
        before = self.pending(self.other_renter, 1, 4)           # ends the day before
        after = self.pending(self.third_renter, 8, 10)           # starts the day after
        other_car = self.make_trip('OTH 1001', 'Hilux', self.today, 5, 7, status='pending')

        response = self.decide(chosen, action='approve')
        self.assertIn('2 overlapping requests were declined automatically.', messages_text(response))

        chosen.refresh_from_db()
        self.assertEqual(chosen.status, 'approved')
        for obj in (touches_start, touches_end):
            obj.refresh_from_db()
            self.assertEqual(obj.status, 'declined')
            self.assertEqual(obj.agency_response, 'Dates no longer available')
            self.assertEqual(obj.decided_at, chosen.decided_at)
        for obj in (before, after, other_car):
            obj.refresh_from_db()
            self.assertEqual(obj.status, 'pending')
            self.assertIsNone(obj.decided_at)

    def test_single_auto_decline_uses_singular_message(self):
        chosen = self.pending(self.renter_user, 5, 7)
        self.pending(self.other_renter, 6, 8)
        response = self.decide(chosen, action='approve')
        self.assertIn('1 overlapping request was declined automatically.', messages_text(response))

    def test_already_decided_booking_unchanged(self):
        for status in ('approved', 'declined', 'cancelled', 'completed'):
            with self.subTest(status=status):
                booking = self.pending(self.renter_user, 40, 41, status=status)
                response = self.decide(booking, action='decline', agency_response='Too late')
                self.assertIn('This request has already been decided.', messages_text(response))
                booking.refresh_from_db()
                self.assertEqual(booking.status, status)
                self.assertEqual(booking.agency_response, '')

    def test_invalid_action_or_long_reply_rejected(self):
        booking = self.pending(self.renter_user, 5, 7)
        for data in ({'action': 'maybe'}, {'action': 'approve', 'agency_response': 'x' * 1001}, {}):
            with self.subTest(data=list(data)):
                response = self.decide(booking, **data)
                self.assertIn('Choose approve or decline.', messages_text(response))
                booking.refresh_from_db()
                self.assertEqual(booking.status, 'pending')
                self.assertIsNone(booking.decided_at)

    def test_other_agency_booking_404(self):
        rival = User.objects.create_user(
            username='rival@example.com', email='rival@example.com', password='password123', is_agency=True,
        )
        AgencyProfile.objects.create(user=rival, business_name='Rival Rentals', contact_number='0917 999 0000')
        booking = self.pending(self.renter_user, 5, 7)
        self.client.force_login(rival)
        self.assertEqual(self.decide(booking, action='approve').status_code, 404)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'pending')

    def test_renter_blocked_from_inbox_and_decide(self):
        booking = self.pending(self.other_renter, 5, 7)
        self.client.force_login(self.renter_user)
        for response in (
            self.client.get(reverse('agencyrequests:inbox')),
            self.decide(booking, action='approve'),
        ):
            self.assertRedirects(response, reverse('home:dashboard'), fetch_redirect_response=False)
            self.assertIn('Only rental agencies', messages_text(response))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'pending')

    def test_get_decide_not_allowed(self):
        booking = self.pending(self.renter_user, 5, 7)
        response = self.client.get(reverse('agencyrequests:decide', args=[booking.pk]))
        self.assertEqual(response.status_code, 405)

    def test_approving_into_an_existing_approved_trip_fails_gracefully(self):
        # Reachable through the view: decide() saves the approval before auto-declining,
        # so the no-overlap constraint rejects it.
        approved = self.pending(self.other_renter, 5, 7, status='approved')
        conflicting = self.pending(self.renter_user, 7, 9)   # pending may overlap
        response = self.decide(conflicting, action='approve', agency_response='Sure')
        self.assertRedirects(response, reverse('agencyrequests:inbox'), fetch_redirect_response=False)
        self.assertIn(
            'Could not approve: the Toyota Innova is already booked for some of those dates.',
            messages_text(response),
        )
        conflicting.refresh_from_db()
        approved.refresh_from_db()
        self.assertEqual(conflicting.status, 'pending')
        self.assertIsNone(conflicting.decided_at)
        self.assertEqual(approved.status, 'approved')


class InboxRenterContactPrivacyTests(BookingStatusTestBase):
    """The inbox respects the renter's "Show contact number" setting."""

    NUMBER = '0917 555 6789'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        User.objects.filter(pk=cls.renter_user.pk).update(contact_number=cls.NUMBER)
        today = timezone.localdate()
        cls.pending_trip = cls.make_trip('PRV 0301', 'Innova', today, 10, 12, status='pending')

    def setUp(self):
        self.client.force_login(self.agency_user)

    def get_inbox(self):
        return self.client.get(reverse('agencyrequests:inbox'))

    def contacts(self, response, section):
        return [b.renter_contact for b in response.context[section]]

    def test_number_shown_when_renter_allows_it(self):
        UserSettings.objects.filter(user=self.renter_user).update(show_contact_number=True)
        response = self.get_inbox()
        self.assertEqual(self.contacts(response, 'pending'), [self.NUMBER])
        # Both the in-progress and the upcoming trip cards show it.
        self.assertEqual(self.contacts(response, 'active'), [self.NUMBER, self.NUMBER])
        self.assertContains(
            response, f'<p class="request-renter-contact">{self.NUMBER}</p>', count=3, html=True
        )

    def test_number_absent_when_renter_hides_it(self):
        UserSettings.objects.filter(user=self.renter_user).update(show_contact_number=False)
        response = self.get_inbox()
        self.assertEqual(self.contacts(response, 'pending'), [''])
        self.assertEqual(self.contacts(response, 'active'), ['', ''])
        self.assertNotContains(response, self.NUMBER)
        self.assertNotContains(response, 'request-renter-contact')

    def test_number_shown_when_renter_has_no_settings_row(self):
        UserSettings.objects.filter(user=self.renter_user).delete()
        response = self.get_inbox()
        self.assertEqual(self.contacts(response, 'pending'), [self.NUMBER])
        self.assertContains(
            response, f'<p class="request-renter-contact">{self.NUMBER}</p>', count=3, html=True
        )
