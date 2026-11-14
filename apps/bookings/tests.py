import datetime
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AgencyProfile
from apps.bookings.lifecycle import (
    AGENCY_CANCEL_PREFIX,
    agency_cancel_reason,
    can_cancel,
    display_status,
    trip_phase,
)
from apps.bookings.models import Booking
from apps.fleet.models import Vehicle
from apps.userprofile.models import DriverLicense
from apps.usersettings.models import UserSettings

User = get_user_model()


class GuestBookingRequestTests(TestCase):
    def test_guest_post_redirects_to_login(self):
        url = reverse('bookings:request', args=[1])
        response = self.client.post(url, {'start_date': '2030-01-01', 'end_date': '2030-01-03'})
        self.assertRedirects(response, f"{reverse('login:login')}?next={url}", fetch_redirect_response=False)


START = datetime.date(2030, 3, 10)
END = datetime.date(2030, 3, 14)
DAY = datetime.timedelta(days=1)


def booking(status, agency_response=''):
    # Unsaved instances are enough: the helpers only read fields.
    return Booking(status=status, start_date=START, end_date=END, agency_response=agency_response)


class TripPhaseTests(SimpleTestCase):
    def test_approved_phases_and_boundaries(self):
        cases = [
            (START - DAY, 'upcoming'),
            (START, 'in_progress'),
            (START + DAY, 'in_progress'),
            (END, 'in_progress'),
            (END + DAY, 'finished'),
        ]
        for today, expected in cases:
            with self.subTest(today=today):
                self.assertEqual(trip_phase(booking('approved'), today), expected)

    def test_none_for_other_statuses(self):
        for status in ('pending', 'declined', 'cancelled', 'completed'):
            with self.subTest(status=status):
                self.assertIsNone(trip_phase(booking(status), START))


class DisplayStatusTests(SimpleTestCase):
    def test_every_branch(self):
        cases = [
            (booking('pending'), START, ('pending', 'Pending')),
            (booking('approved'), START - DAY, ('upcoming', 'Upcoming')),
            (booking('approved'), START, ('in_progress', 'In progress')),
            (booking('approved'), END, ('in_progress', 'In progress')),
            (booking('approved'), END + DAY, ('completed', 'Completed')),
            (booking('completed'), START - DAY, ('completed', 'Completed')),
            (booking('declined'), START, ('declined', 'Declined')),
            (booking('cancelled'), START, ('cancelled', 'Cancelled')),
            (booking('cancelled', 'Changed my plans'), START, ('cancelled', 'Cancelled')),
            (booking('cancelled', f'{AGENCY_CANCEL_PREFIX}Car needs repairs.'), START, ('cancelled', 'Cancelled by agency')),
        ]
        for obj, today, expected in cases:
            with self.subTest(status=obj.status, today=today, response=obj.agency_response):
                self.assertEqual(display_status(obj, today), expected)


class CanCancelTests(SimpleTestCase):
    def test_pending_always_cancellable(self):
        for today in (START - DAY, START, END + DAY):
            with self.subTest(today=today):
                self.assertTrue(can_cancel(booking('pending'), today))

    def test_approved_only_before_start(self):
        self.assertTrue(can_cancel(booking('approved'), START - DAY))
        self.assertFalse(can_cancel(booking('approved'), START))
        self.assertFalse(can_cancel(booking('approved'), END))
        self.assertFalse(can_cancel(booking('approved'), END + DAY))

    def test_other_statuses_never(self):
        for status in ('declined', 'cancelled', 'completed'):
            with self.subTest(status=status):
                self.assertFalse(can_cancel(booking(status), START - DAY))


class AgencyCancelReasonTests(SimpleTestCase):
    def test_reason_after_prefix(self):
        obj = booking('cancelled', f'{AGENCY_CANCEL_PREFIX}Car needs repairs.')
        self.assertEqual(agency_cancel_reason(obj), 'Car needs repairs.')

    def test_empty_when_not_cancelled_by_agency(self):
        cases = [
            booking('cancelled'),
            booking('cancelled', 'Renter changed plans'),
            booking('declined', f'{AGENCY_CANCEL_PREFIX}Not a cancel'),
            booking('approved', f'{AGENCY_CANCEL_PREFIX}Not a cancel'),
        ]
        for obj in cases:
            with self.subTest(status=obj.status, response=obj.agency_response):
                self.assertEqual(agency_cancel_reason(obj), '')


class NotificationTestBase(TestCase):
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
        cls.renter = cls.make_renter('maria@example.com', 'Maria')
        cls.other_renter = cls.make_renter('paolo@example.com', 'Paolo')
        cls.vehicle = Vehicle.objects.create(
            agency=cls.agency_profile,
            make='Toyota',
            model='Vios',
            year=2022,
            plate_number='ABC 1234',
            transmission='Automatic',
            fuel_type='Gasoline',
            seats=5,
            color='White',
            daily_rate=Decimal('2500.00'),
            city='Cebu City',
        )

    @staticmethod
    def make_renter(email, first_name):
        user = User.objects.create_user(
            username=email, email=email, password='password123', is_renter=True, first_name=first_name,
        )
        DriverLicense.objects.create(
            user=user,
            license_number=f'N01-{first_name}',
            issuing_country='Philippines',
            expiry_date=timezone.localdate() + datetime.timedelta(days=365),
            license_image='userprofile/licenses/test.png',
        )
        return user

    def setUp(self):
        self.today = timezone.localdate()

    def make_booking(self, renter, start_offset, end_offset, status='pending', **extra):
        return Booking.objects.create(
            vehicle=self.vehicle,
            renter=renter,
            start_date=self.today + datetime.timedelta(days=start_offset),
            end_date=self.today + datetime.timedelta(days=end_offset),
            daily_rate_snapshot=self.vehicle.daily_rate,
            status=status,
            **extra,
        )

    def post(self, user, url_name, pk, data=None):
        """POST as `user` and run the on_commit callbacks, so emails are sent."""
        self.client.force_login(user)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse(url_name, args=[pk]), data or {})

    def emails_to(self, address):
        return [m for m in mail.outbox if address in m.to]


class BookingEventEmailTests(NotificationTestBase):
    def test_new_request_emails_agency(self):
        start = self.today + datetime.timedelta(days=5)
        end = start + datetime.timedelta(days=2)
        self.post(self.renter, 'bookings:request', self.vehicle.pk, {
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
            'renter_message': "I'll pick it up at 9.",
        })
        self.assertEqual(Booking.objects.filter(renter=self.renter, status='pending').count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['agency@example.com'])
        self.assertEqual(email.from_email, 'AutoLease <no-reply@autolease.local>')
        self.assertIn('New booking request: Toyota Vios', email.subject)
        self.assertIn(f'{start:%b} {start.day}–{end:%b} {end.day}', email.subject)
        self.assertIn('Maria would like to rent', email.body)
        self.assertIn('(3 days)', email.body)
        self.assertIn('₱7,500', email.body)
        self.assertIn("I'll pick it up at 9.", email.body)  # not HTML-escaped
        self.assertIn('http://testserver/agency/requests/', email.body)
        self.assertIn('The AutoLease team', email.body)

    def test_approve_emails_renter_and_auto_declined_renters(self):
        booking = self.make_booking(self.renter, 5, 7)
        overlapping = self.make_booking(self.other_renter, 6, 8)
        third_renter = self.make_renter('ana@example.com', 'Ana')
        also_overlapping = self.make_booking(third_renter, 4, 5)
        not_overlapping = self.make_booking(self.other_renter, 20, 21)

        self.post(self.agency_user, 'agencyrequests:decide', booking.pk, {
            'action': 'approve', 'agency_response': 'See you at the airport.',
        })
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'approved')

        confirmed = self.emails_to('maria@example.com')
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0].subject, 'Your trip is confirmed: Toyota Vios')
        self.assertIn('See you at the airport.', confirmed[0].body)
        self.assertIn('http://testserver/my-bookings/', confirmed[0].body)

        for address, obj in (('paolo@example.com', overlapping), ('ana@example.com', also_overlapping)):
            with self.subTest(address=address):
                declined = self.emails_to(address)
                self.assertEqual(len(declined), 1)
                self.assertEqual(declined[0].subject, "Your request wasn't accepted: Toyota Vios")
                obj.refresh_from_db()
                self.assertEqual(obj.status, 'declined')
        not_overlapping.refresh_from_db()
        self.assertEqual(not_overlapping.status, 'pending')
        self.assertEqual(len(mail.outbox), 3)

    def test_decline_emails_renter(self):
        booking = self.make_booking(self.renter, 5, 7)
        self.post(self.agency_user, 'agencyrequests:decide', booking.pk, {
            'action': 'decline', 'agency_response': 'Fully booked that week.',
        })
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['maria@example.com'])
        self.assertEqual(email.subject, "Your request wasn't accepted: Toyota Vios")
        self.assertIn('Fully booked that week.', email.body)
        self.assertIn('Hi Maria,', email.body)

    def test_car_to_maintenance_emails_auto_declined_renters(self):
        self.make_booking(self.renter, 5, 7)
        self.make_booking(self.other_renter, 10, 11)
        self.post(self.agency_user, 'agencyfleet:status', self.vehicle.pk, {'status': 'maintenance'})
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, 'maintenance')
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ['maria@example.com', 'paolo@example.com'])
        for email in mail.outbox:
            self.assertEqual(email.subject, "Your request wasn't accepted: Toyota Vios")
            self.assertIn('This car is no longer available.', email.body)

    def test_renter_cancels_approved_trip_emails_agency(self):
        booking = self.make_booking(self.renter, 5, 7, status='approved')
        self.post(self.renter, 'mybookings:cancel', booking.pk)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['agency@example.com'])
        self.assertIn('Trip cancelled by renter: Toyota Vios', email.subject)
        self.assertIn('Maria cancelled an approved trip.', email.body)

    def test_renter_cancels_pending_request_sends_nothing(self):
        booking = self.make_booking(self.renter, 5, 7)
        self.post(self.renter, 'mybookings:cancel', booking.pk)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(mail.outbox, [])

    def test_agency_cancels_trip_emails_renter_with_reason(self):
        booking = self.make_booking(self.renter, 5, 7, status='approved')
        self.post(self.agency_user, 'agencyrequests:cancel', booking.pk, {'reason': "The car's brakes need work."})
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['maria@example.com'])
        self.assertEqual(email.subject, 'Your trip was cancelled by the agency: Toyota Vios')
        self.assertIn("Reason: The car's brakes need work.", email.body)
        self.assertNotIn(AGENCY_CANCEL_PREFIX, email.body)

    def test_no_email_when_nothing_commits(self):
        # Without running on_commit callbacks, nothing is sent yet.
        booking = self.make_booking(self.renter, 5, 7)
        self.client.force_login(self.agency_user)
        self.client.post(reverse('agencyrequests:decide', args=[booking.pk]), {'action': 'decline'})
        self.assertEqual(mail.outbox, [])


class NotificationOptOutAndFailureTests(NotificationTestBase):
    def test_opted_out_recipient_gets_nothing_but_action_succeeds(self):
        UserSettings.objects.filter(user=self.renter).update(email_notifications=False)
        booking = self.make_booking(self.renter, 5, 7)
        overlapping = self.make_booking(self.other_renter, 6, 8)

        self.post(self.agency_user, 'agencyrequests:decide', booking.pk, {'action': 'approve'})
        booking.refresh_from_db()
        overlapping.refresh_from_db()
        self.assertEqual(booking.status, 'approved')
        self.assertEqual(overlapping.status, 'declined')
        self.assertEqual(self.emails_to('maria@example.com'), [])
        self.assertEqual(len(self.emails_to('paolo@example.com')), 1)

    def test_agency_opt_out(self):
        UserSettings.objects.filter(user=self.agency_user).update(email_notifications=False)
        booking = self.make_booking(self.renter, 5, 7, status='approved')
        self.post(self.renter, 'mybookings:cancel', booking.pk)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(mail.outbox, [])

    def test_missing_settings_row_defaults_to_sending(self):
        UserSettings.objects.filter(user=self.renter).delete()
        booking = self.make_booking(self.renter, 5, 7)
        self.post(self.agency_user, 'agencyrequests:decide', booking.pk, {'action': 'decline'})
        self.assertEqual(len(self.emails_to('maria@example.com')), 1)

    def test_user_without_email_gets_nothing(self):
        User.objects.filter(pk=self.renter.pk).update(email='')
        booking = self.make_booking(self.renter, 5, 7)
        self.post(self.agency_user, 'agencyrequests:decide', booking.pk, {'action': 'decline'})
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'declined')
        self.assertEqual(mail.outbox, [])

    def test_send_failure_never_breaks_or_rolls_back_the_action(self):
        booking = self.make_booking(self.renter, 5, 7)
        overlapping = self.make_booking(self.other_renter, 6, 8)
        with mock.patch('apps.bookings.notifications.send_mail', side_effect=OSError('SMTP down')) as send:
            with self.assertLogs('apps.bookings.notifications', level='ERROR') as logs:
                response = self.post(self.agency_user, 'agencyrequests:decide', booking.pk, {'action': 'approve'})
        self.assertEqual(send.call_count, 2)
        self.assertEqual(len(logs.records), 2)
        self.assertRedirects(response, reverse('agencyrequests:inbox'), fetch_redirect_response=False)
        booking.refresh_from_db()
        overlapping.refresh_from_db()
        self.assertEqual(booking.status, 'approved')
        self.assertEqual(overlapping.status, 'declined')

    def test_send_failure_on_new_request_still_creates_booking(self):
        start = self.today + datetime.timedelta(days=5)
        with mock.patch('apps.bookings.notifications.send_mail', side_effect=Exception('boom')):
            with self.assertLogs('apps.bookings.notifications', level='ERROR'):
                response = self.post(self.renter, 'bookings:request', self.vehicle.pk, {
                    'start_date': start.isoformat(),
                    'end_date': start.isoformat(),
                })
        self.assertRedirects(response, reverse('mybookings:list'), fetch_redirect_response=False)
        self.assertTrue(Booking.objects.filter(renter=self.renter, status='pending').exists())
