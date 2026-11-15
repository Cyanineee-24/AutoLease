import datetime
import unittest
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core import mail
from django.db import IntegrityError, transaction
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
from apps.bookings.models import Booking, Review
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


def messages_text(response):
    return ' '.join(str(m) for m in get_messages(response.wsgi_request))


class BookingRequestRulesTests(NotificationTestBase):
    """The original request rules of bookings:request / BookingRequestForm."""

    def request(self, user, start_offset, end_offset, message='', vehicle=None):
        vehicle = vehicle or self.vehicle
        self.client.force_login(user)
        data = {
            'start_date': (self.today + datetime.timedelta(days=start_offset)).isoformat(),
            'end_date': (self.today + datetime.timedelta(days=end_offset)).isoformat(),
            'renter_message': message,
        }
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('bookings:request', args=[vehicle.pk]), data)

    def assert_refused(self, response, message, renter=None):
        self.assertEqual(response.status_code, 302)
        self.assertIn(message, messages_text(response))
        self.assertFalse(Booking.objects.filter(renter=renter or self.renter).exists())

    def test_happy_path_creates_pending_booking_with_rate_snapshot(self):
        response = self.request(self.renter, 5, 8, message='Airport pick-up, please.')
        self.assertRedirects(response, reverse('mybookings:list'), fetch_redirect_response=False)
        self.assertIn('Request sent for 4 days.', messages_text(response))

        booking = Booking.objects.get(renter=self.renter)
        self.assertEqual(booking.status, 'pending')
        self.assertEqual(booking.vehicle, self.vehicle)
        self.assertEqual(booking.start_date, self.today + datetime.timedelta(days=5))
        self.assertEqual(booking.end_date, self.today + datetime.timedelta(days=8))
        self.assertEqual(booking.renter_message, 'Airport pick-up, please.')
        self.assertEqual(booking.daily_rate_snapshot, Decimal('2500.00'))

        # A later price change does not touch the request.
        Vehicle.objects.filter(pk=self.vehicle.pk).update(daily_rate=Decimal('9999.00'))
        booking.refresh_from_db()
        self.assertEqual(booking.daily_rate_snapshot, Decimal('2500.00'))

    def test_same_day_trip_allowed_as_one_day(self):
        response = self.request(self.renter, 3, 3)
        self.assertIn('Request sent for 1 day.', messages_text(response))
        self.assertEqual(Booking.objects.filter(renter=self.renter, status='pending').count(), 1)

    def test_owner_cannot_request_own_car(self):
        DriverLicense.objects.create(
            user=self.agency_user,
            license_number='N01-AGENCY',
            issuing_country='Philippines',
            expiry_date=self.today + datetime.timedelta(days=365),
            license_image='userprofile/licenses/test.png',
        )
        response = self.request(self.agency_user, 3, 4)
        self.assert_refused(response, "You can't request your own car.", renter=self.agency_user)

    def test_no_license_refused(self):
        no_license = User.objects.create_user(
            username='nolicense@example.com', email='nolicense@example.com', password='password123', is_renter=True,
        )
        response = self.request(no_license, 3, 4)
        self.assert_refused(response, "Add your driver's license to your profile before requesting a car.", renter=no_license)

    def test_past_pick_up_refused(self):
        self.assert_refused(self.request(self.renter, -1, 2), 'Pick-up date cannot be in the past.')

    def test_drop_off_before_pick_up_refused(self):
        self.assert_refused(self.request(self.renter, 5, 4), 'Drop-off must be on or after pick-up.')

    def test_overlap_with_approved_booking_refused_inclusive_edge(self):
        self.make_booking(self.other_renter, 5, 7, status='approved')
        # New trip starts on the day the approved one ends.
        response = self.request(self.renter, 7, 9)
        self.assert_refused(response, 'This car is already booked for some of those dates.')

    def test_overlap_with_someone_elses_pending_request_allowed(self):
        other = self.make_booking(self.other_renter, 5, 7)
        response = self.request(self.renter, 6, 8)
        self.assertIn('Request sent for 3 days.', messages_text(response))
        other.refresh_from_db()
        self.assertEqual(other.status, 'pending')
        self.assertEqual(Booking.objects.get(renter=self.renter).status, 'pending')

    def test_same_renter_overlapping_pending_refused(self):
        self.make_booking(self.renter, 5, 7)
        response = self.request(self.renter, 7, 9)
        self.assertIn('You already have a pending request for these dates.', messages_text(response))
        self.assertEqual(Booking.objects.filter(renter=self.renter).count(), 1)

    def test_unavailable_or_maintenance_car_404(self):
        for status in ('unavailable', 'maintenance'):
            with self.subTest(status=status):
                Vehicle.objects.filter(pk=self.vehicle.pk).update(status=status)
                response = self.request(self.renter, 3, 4)
                self.assertEqual(response.status_code, 404)
                self.assertFalse(Booking.objects.filter(renter=self.renter).exists())

    # BUG: apps/bookings/forms.py:19 sets max_length after the field is built, so no MaxLengthValidator runs.
    @unittest.expectedFailure
    def test_message_over_1000_characters_refused(self):
        response = self.request(self.renter, 3, 4, message='x' * 1001)
        self.assertEqual(response.status_code, 302)
        self.assertIn('Ensure this value has at most 1000 characters', messages_text(response))
        self.assertFalse(Booking.objects.filter(renter=self.renter).exists())

    def test_get_not_allowed(self):
        self.client.force_login(self.renter)
        response = self.client.get(reverse('bookings:request', args=[self.vehicle.pk]))
        self.assertEqual(response.status_code, 405)


class BookingConstraintTests(NotificationTestBase):
    """Database constraints, checked at the model level (fixed past dates are fine here)."""

    START = datetime.date(2024, 3, 10)
    END = datetime.date(2024, 3, 14)

    def booking(self, renter=None, start=START, end=END, status='approved', vehicle=None):
        return Booking(
            vehicle=vehicle or self.vehicle,
            renter=renter or self.renter,
            start_date=start,
            end_date=end,
            daily_rate_snapshot=Decimal('2500.00'),
            status=status,
        )

    def assert_integrity_error(self, obj):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                obj.save()

    def test_two_approved_bookings_cannot_overlap(self):
        self.booking().save()
        day = datetime.timedelta(days=1)
        for start, end in (
            (self.START, self.END),                    # identical
            (self.START + day, self.END - day),        # inside
            (self.START - 3 * day, self.START),        # touches the first day
            (self.END, self.END + 3 * day),            # touches the last day
        ):
            with self.subTest(start=start, end=end):
                self.assert_integrity_error(self.booking(self.other_renter, start, end))

    def test_adjacent_approved_bookings_are_fine(self):
        self.booking().save()
        day = datetime.timedelta(days=1)
        self.booking(self.other_renter, self.END + day, self.END + 3 * day).save()
        self.booking(self.other_renter, self.START - 3 * day, self.START - day).save()
        self.assertEqual(Booking.objects.filter(status='approved').count(), 3)

    def test_same_dates_on_a_different_car_are_fine(self):
        other_car = Vehicle.objects.create(
            agency=self.agency_profile, make='Honda', model='City', year=2021, plate_number='XYZ 9876',
            transmission='Automatic', fuel_type='Gasoline', seats=5, color='Gray',
            daily_rate=Decimal('2800.00'), city='Cebu City',
        )
        self.booking().save()
        self.booking(self.other_renter, vehicle=other_car).save()
        self.assertEqual(Booking.objects.filter(status='approved').count(), 2)

    def test_overlap_allowed_when_one_is_not_approved(self):
        self.booking().save()
        for status in ('pending', 'declined', 'cancelled'):
            with self.subTest(status=status):
                self.booking(self.other_renter, status=status).save()
        self.assertEqual(Booking.objects.count(), 4)

    def test_end_before_start_rejected(self):
        self.assert_integrity_error(self.booking(start=self.END, end=self.START, status='pending'))

    def test_invalid_status_rejected(self):
        self.assert_integrity_error(self.booking(status='weird'))

    def test_review_rating_must_be_1_to_5(self):
        booking = self.booking(status='completed')
        booking.save()
        for rating in (0, 6):
            with self.subTest(rating=rating):
                self.assert_integrity_error(Review(booking=booking, rating=rating))
        for rating in (1, 5):
            with self.subTest(rating=rating):
                with transaction.atomic():
                    review = Review.objects.create(booking=booking, rating=rating)
                    review.delete()
