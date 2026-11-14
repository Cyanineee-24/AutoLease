import datetime

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.bookings.lifecycle import (
    AGENCY_CANCEL_PREFIX,
    agency_cancel_reason,
    can_cancel,
    display_status,
    trip_phase,
)
from apps.bookings.models import Booking


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
