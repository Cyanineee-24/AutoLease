import datetime

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import connection
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from apps.accounts.models import AgencyProfile
from apps.bookings.lifecycle import AGENCY_CANCEL_PREFIX
from apps.bookings.models import Booking
from apps.mybookings.tests import BookingStatusTestBase
from apps.usersettings.models import UserSettings

from .views import _join_with_and, _short_range

User = get_user_model()


def messages_text(response):
    return ' '.join(str(m) for m in get_messages(response.wsgi_request))


class InboxHistoryStatusLabelTests(BookingStatusTestBase):
    def test_history_shows_date_based_labels(self):
        self.client.force_login(self.agency_user)
        response = self.client.get(reverse('agencyrequests:inbox'))
        self.assertEqual(response.status_code, 200)
        rows = response.context['bookings']
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


class InboxCardsTests(BookingStatusTestBase):
    """One grid of cards; each card's group decides what its action bar offers."""

    def setUp(self):
        self.client.force_login(self.agency_user)
        self.today = timezone.localdate()

    def test_inbox_groups_pending_upcoming_in_progress_and_past(self):
        pending = self.make_trip('PEN 0201', 'Innova', self.today, 3, 4, status='pending')
        declined = self.make_trip('DEC 0202', 'Hilux', self.today, 3, 4, status='declined')
        response = self.client.get(reverse('agencyrequests:inbox'))

        self.assertEqual(
            {b.pk: b.group for b in response.context['bookings']},
            {
                pending.pk: 'pending',
                self.future_trip.pk: 'upcoming',
                self.current_trip.pk: 'in_progress',
                self.past_trip.pk: 'past',
                declined.pk: 'past',
            },
        )
        self.assertEqual(
            response.context['status_counts'],
            {'all': 5, 'pending': 1, 'upcoming': 1, 'in_progress': 1, 'past': 2},
        )
        # "Upcoming trips" in the subtitle counts the trips still ahead or under way.
        self.assertContains(response, '1 awaiting your decision · 2 upcoming trips')
        self.assertContains(response, '<li class="request-card">', count=5)

    def test_only_upcoming_trip_has_cancel_form(self):
        response = self.client.get(reverse('agencyrequests:inbox'))
        self.assertContains(response, reverse('agencyrequests:cancel', args=[self.future_trip.pk]))
        self.assertNotContains(response, reverse('agencyrequests:cancel', args=[self.current_trip.pk]))
        self.assertNotContains(response, reverse('agencyrequests:cancel', args=[self.past_trip.pk]))
        self.assertContains(response, "Trip in progress. It can't be cancelled.")
        self.assertContains(response, 'Why are you cancelling?')
        self.assertContains(response, 'Juan will see this.')
        self.assertContains(response, 'js/confirm.js')

    def test_cancel_form_has_no_confirm_and_still_requires_a_reason(self):
        response = self.client.get(reverse('agencyrequests:inbox'))
        html = response.content.decode()
        action = f'action="{reverse("agencyrequests:cancel", args=[self.future_trip.pk])}"'
        form_start = html.rindex('<form', 0, html.index(action))
        form = html[form_start:html.index('</form>', form_start)]
        # The open reason box is the confirmation, so the themed dialog is not used here.
        self.assertNotIn('data-confirm', form)
        self.assertIn('name="reason"', form)
        self.assertIn(' required ', form)
        self.assertIn('Confirm cancellation', form)
        # And the server still refuses an empty reason.
        refused = self.client.post(reverse('agencyrequests:cancel', args=[self.future_trip.pk]), {'reason': ''})
        self.assertIn("Tell the renter why you're cancelling.", messages_text(refused))
        self.future_trip.refresh_from_db()
        self.assertEqual(self.future_trip.status, 'approved')

    def test_no_cancel_forms_when_no_active_trips(self):
        Booking.objects.filter(pk__in=[self.future_trip.pk, self.current_trip.pk]).update(status='declined')
        response = self.client.get(reverse('agencyrequests:inbox'))
        self.assertNotContains(response, 'Confirm cancellation')
        self.assertContains(response, '0 awaiting your decision · 0 upcoming trips')

    def test_past_cards_show_reply_or_reason_without_the_stored_prefix(self):
        declined = self.make_trip('DEC 0203', 'Hilux', self.today, 3, 4, status='declined')
        Booking.objects.filter(pk=declined.pk).update(agency_response='Fully booked that week.')
        Booking.objects.filter(pk=self.future_trip.pk).update(
            status='cancelled', agency_response=f'{AGENCY_CANCEL_PREFIX}The car failed inspection.',
        )
        response = self.client.get(reverse('agencyrequests:inbox'))
        self.assertContains(response, 'Your reply: “Fully booked that week.”')
        self.assertContains(response, 'Your reason: “The car failed inspection.”')
        self.assertNotContains(response, AGENCY_CANCEL_PREFIX)

    def test_query_count_does_not_grow_with_bookings(self):
        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get(reverse('agencyrequests:inbox'))
            self.assertEqual(response.status_code, 200)
            return len(ctx.captured_queries)

        baseline = count_queries()
        for index in range(4):
            self.make_trip(f'QRY {index:04d}', 'Innova', self.today, 20 + index, 21 + index, status='pending')
            self.make_trip(f'QRZ {index:04d}', 'Hilux', self.today, 30 + index, 31 + index, status='approved')
        self.assertEqual(count_queries(), baseline)


class InboxFilterTests(BookingStatusTestBase):
    """Status chips, the car filter and sorting."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        today = timezone.localdate()
        cls.pending = cls.make_trip('PEN 0401', 'Innova', today, 3, 4, status='pending')
        cls.declined = cls.make_trip('DEC 0402', 'Hilux', today, 3, 4, status='declined')
        cls.cancelled = cls.make_trip('CAN 0403', 'Jimny', today, 12, 13, status='cancelled')

        # Another agency with its own car and booking, which must never show up.
        cls.rival_user = User.objects.create_user(
            username='rival@example.com', email='rival@example.com', password='password123', is_agency=True,
        )
        own_profile = cls.agency_profile
        cls.agency_profile = AgencyProfile.objects.create(
            user=cls.rival_user, business_name='Rival Rentals', contact_number='0917 999 0000',
        )
        cls.rival_booking = cls.make_trip('RIV 0404', 'Raize', today, 3, 4, status='pending')
        cls.agency_profile = own_profile

        # Fixed, distinct created_at values so "newest first" is unambiguous.
        base = timezone.now() - datetime.timedelta(days=10)
        cls.by_age = [cls.past_trip, cls.current_trip, cls.future_trip, cls.pending, cls.declined, cls.cancelled]
        for index, booking in enumerate(cls.by_age):
            Booking.objects.filter(pk=booking.pk).update(created_at=base + datetime.timedelta(hours=index))

    def setUp(self):
        self.client.force_login(self.agency_user)
        self.url = reverse('agencyrequests:inbox')

    def pks(self, response):
        return [b.pk for b in response.context['bookings']]

    def test_each_status_filter_returns_the_right_bookings(self):
        expected = {
            'all': {b.pk for b in self.by_age},
            'pending': {self.pending.pk},
            'upcoming': {self.future_trip.pk},
            'in_progress': {self.current_trip.pk},
            'past': {self.past_trip.pk, self.declined.pk, self.cancelled.pk},
        }
        counts = {'all': 6, 'pending': 1, 'upcoming': 1, 'in_progress': 1, 'past': 3}
        for status, pks in expected.items():
            with self.subTest(status=status):
                response = self.client.get(self.url, {'status': status})
                self.assertEqual(set(self.pks(response)), pks)
                self.assertEqual(response.context['current_status'], status)
                # The chip counts don't change with the chosen status.
                self.assertEqual(response.context['status_counts'], counts)

    def test_chips_show_counts_and_mark_the_active_one(self):
        response = self.client.get(self.url, {'status': 'past'})
        self.assertContains(response, '<div class="filter-chips" role="group" aria-label="Filter by status">')
        self.assertContains(response, f'<a class="filter-chip" href="{self.url}">All · 6</a>', html=True)
        self.assertContains(
            response, f'<a class="filter-chip" href="{self.url}?status=past" aria-current="true">Past · 3</a>', html=True,
        )
        self.assertContains(response, 'aria-current="true"', count=1)
        self.assertContains(response, 'In progress · 1')

    def test_invalid_status_and_sort_fall_back(self):
        response = self.client.get(self.url, {'status': 'banana', 'sort': 'sideways'})
        self.assertEqual(response.context['current_status'], 'all')
        self.assertEqual(response.context['current_sort'], 'newest')
        self.assertEqual(len(self.pks(response)), 6)

    def test_car_filter_narrows_results_and_counts(self):
        car = self.pending.vehicle
        response = self.client.get(self.url, {'car': car.pk})
        self.assertEqual(self.pks(response), [self.pending.pk])
        self.assertEqual(response.context['current_car'], car.pk)
        self.assertEqual(
            response.context['status_counts'],
            {'all': 1, 'pending': 1, 'upcoming': 0, 'in_progress': 0, 'past': 0},
        )
        # The chips and the hidden field keep the other filters.
        response = self.client.get(self.url, {'car': car.pk, 'status': 'past', 'sort': 'pickup'})
        self.assertEqual(self.pks(response), [])
        self.assertContains(response, f'href="{self.url}?status=pending&amp;car={car.pk}&amp;sort=pickup"')
        self.assertContains(response, '<input type="hidden" name="status" value="past">', html=True)
        self.assertContains(response, 'Nothing matches these filters.')
        self.assertContains(response, f'<a class="inbox-clear" href="{self.url}">Clear filters</a>', html=True)

    def test_other_agency_car_and_junk_car_values_are_ignored(self):
        for value in (self.rival_booking.vehicle.pk, 'abc', '-1', '999999999', '1 OR 1=1', ''):
            with self.subTest(car=value):
                response = self.client.get(self.url, {'car': value})
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.context['current_car'])
                self.assertEqual(len(self.pks(response)), 6)
                self.assertNotIn(self.rival_booking.pk, self.pks(response))
        # The car select lists only this agency's cars.
        self.assertNotIn(self.rival_booking.vehicle, response.context['cars'])
        self.assertNotContains(response, 'Raize')

    def test_sort_newest_first_by_default_and_by_pick_up_date(self):
        response = self.client.get(self.url)
        self.assertEqual(self.pks(response), [b.pk for b in reversed(self.by_age)])

        response = self.client.get(self.url, {'sort': 'pickup'})
        # By start_date; the two that start the same day keep created_at order.
        self.assertEqual(
            self.pks(response),
            [self.past_trip.pk, self.current_trip.pk, self.pending.pk, self.declined.pk,
             self.future_trip.pk, self.cancelled.pk],
        )
        self.assertEqual(response.context['current_sort'], 'pickup')

    def test_empty_inbox_message(self):
        Booking.objects.filter(vehicle__agency=self.agency_profile).delete()
        response = self.client.get(self.url)
        self.assertContains(response, "No booking requests yet. They'll show up here when renters ask for your cars.")
        self.assertNotContains(response, 'Nothing matches these filters.')


class InboxOverlapTests(BookingStatusTestBase):
    """What a pending card says about other bookings on the same car and dates."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.paolo = User.objects.create_user(
            username='paolo@example.com', email='paolo@example.com', password='password123',
            is_renter=True, first_name='Paolo',
        )
        cls.ana = User.objects.create_user(
            username='ana@example.com', email='ana@example.com', password='password123',
            is_renter=True, first_name='Ana',
        )

    def setUp(self):
        self.today = timezone.localdate()
        self.client.force_login(self.agency_user)
        self.url = reverse('agencyrequests:inbox')
        # A car with no approved trips.
        self.car = self.make_trip('OVL 1000', 'Innova', self.today, 60, 61, status='declined').vehicle

    def book(self, renter, start_offset, end_offset, status='pending'):
        return Booking.objects.create(
            vehicle=self.car,
            renter=renter,
            start_date=self.today + datetime.timedelta(days=start_offset),
            end_date=self.today + datetime.timedelta(days=end_offset),
            daily_rate_snapshot=self.car.daily_rate,
            status=status,
        )

    def card(self, response, booking):
        return next(b for b in response.context['bookings'] if b.pk == booking.pk)

    def approve_button(self, **attrs):
        extra = ''.join(f' {name}="{value}"' for name, value in attrs.items())
        return f'<button type="submit" name="action" value="approve" class="button"{extra}>Approve</button>'

    def test_overlapping_pending_requests_warn_and_confirm(self):
        chosen = self.book(self.renter_user, 5, 7)
        paolo = self.book(self.paolo, 6, 8)
        ana = self.book(self.ana, 7, 9)       # touches chosen's last day
        self.book(self.paolo, 20, 21)         # same car, other dates
        self.make_trip('OTH 1001', 'Hilux', self.today, 5, 7, status='pending')  # other car, same dates

        response = self.client.get(self.url)
        card = self.card(response, chosen)
        self.assertEqual([b.pk for b in card.overlapping_pending], [paolo.pk, ana.pk])
        self.assertIsNone(card.blocking_trip)

        expected_text = (
            f'Approving Juan automatically declines '
            f'Paolo ({_short_range(paolo.start_date, paolo.end_date)}) and '
            f'Ana ({_short_range(ana.start_date, ana.end_date)}). '
            "They'll be told the dates are no longer available."
        )
        self.assertEqual(card.approve_confirm_text, expected_text)
        self.assertContains(response, f'data-confirm="{escape(expected_text)}"')
        self.assertContains(response, 'data-confirm-title="Approve and decline 2 other requests?"')
        self.assertContains(response, 'data-confirm-action="Approve and decline 2"')
        self.assertContains(response, 'Overlaps 2 other pending requests.')
        self.assertContains(response, f'href="{self.url}?status=pending&amp;car={self.car.pk}">See them</a>')

        # The warning names exactly what approving then declines.
        with self.captureOnCommitCallbacks(execute=True):
            decided = self.client.post(reverse('agencyrequests:decide', args=[chosen.pk]), {'action': 'approve'})
        self.assertIn('2 overlapping requests were declined automatically.', messages_text(decided))

    def test_single_overlap_uses_singular_wording(self):
        chosen = self.book(self.renter_user, 5, 7)
        self.book(self.paolo, 7, 8)
        response = self.client.get(self.url)
        self.assertEqual(len(self.card(response, chosen).overlapping_pending), 1)
        self.assertContains(response, 'Overlaps 1 other pending request.')
        self.assertContains(response, 'data-confirm-title="Approve and decline 1 other request?"')
        self.assertContains(response, 'data-confirm-action="Approve and decline 1"')

    def test_clash_with_approved_trip_disables_approve(self):
        trip = self.book(self.paolo, 5, 7, status='approved')
        request = self.book(self.renter_user, 7, 9)
        response = self.client.get(self.url)
        card = self.card(response, request)
        self.assertEqual(card.blocking_trip.pk, trip.pk)
        clash = (
            f"Clashes with Paolo's approved trip on {_short_range(trip.start_date, trip.end_date)}. "
            'Decline this request, or cancel that trip first.'
        )
        self.assertEqual(card.clash_text, clash)
        self.assertContains(response, escape(clash))
        self.assertContains(response, f'<p class="request-warning" id="clash-{request.pk}">')
        self.assertContains(
            response,
            '<button type="submit" name="action" value="approve" class="button" disabled '
            f'aria-describedby="clash-{request.pk}">Approve</button>',
            html=True,
        )
        # Decline still works, and the server refuses a forced approve.
        self.assertContains(response, 'data-confirm-action="Decline request"', count=1)
        with self.captureOnCommitCallbacks(execute=True):
            forced = self.client.post(reverse('agencyrequests:decide', args=[request.pk]), {'action': 'approve'})
        self.assertIn('Could not approve', messages_text(forced))

    def test_no_overlap_approve_has_no_confirm(self):
        request = self.book(self.renter_user, 5, 7)
        self.book(self.paolo, 8, 9)   # the day after: no overlap
        response = self.client.get(self.url, {'car': self.car.pk, 'status': 'pending'})
        card = self.card(response, request)
        self.assertEqual(card.overlapping_pending, [])
        self.assertIsNone(card.blocking_trip)
        self.assertContains(response, self.approve_button(), count=2, html=True)
        self.assertNotContains(response, 'Approve and decline')
        self.assertNotContains(response, 'Overlaps')

    def test_decline_has_its_own_confirm(self):
        self.book(self.renter_user, 5, 7)
        response = self.client.get(self.url)
        self.assertContains(
            response,
            '<button type="submit" name="action" value="decline" class="button-outline" '
            'data-confirm-title="Decline this request?" '
            'data-confirm="Juan will be told. This can\'t be undone." '
            'data-confirm-action="Decline request" data-confirm-danger>Decline</button>',
            html=True,
        )
        # The form itself asks nothing, so a plain Approve submits straight away.
        html = response.content.decode()
        form_tag = html[html.index('class="request-actions request-decide"') - 200:]
        form_tag = form_tag[form_tag.index('<form'):form_tag.index('>', form_tag.index('<form'))]
        self.assertNotIn('data-confirm', form_tag)


class InboxHelperTests(SimpleTestCase):
    def test_short_range(self):
        day = datetime.date
        self.assertEqual(_short_range(day(2026, 11, 21), day(2026, 11, 26)), 'Nov 21 – 26')
        self.assertEqual(_short_range(day(2026, 11, 28), day(2026, 12, 2)), 'Nov 28 – Dec 2')
        self.assertEqual(_short_range(day(2026, 12, 30), day(2027, 1, 2)), 'Dec 30, 2026 – Jan 2, 2027')
        self.assertEqual(_short_range(day(2026, 11, 21), day(2026, 11, 21)), 'Nov 21')

    def test_join_with_and(self):
        self.assertEqual(_join_with_and(['Ana']), 'Ana')
        self.assertEqual(_join_with_and(['Ana', 'Paolo']), 'Ana and Paolo')
        self.assertEqual(_join_with_and(['Ana', 'Paolo', 'Juan']), 'Ana, Paolo and Juan')


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

        # The agency's past cards show the same label.
        self.client.force_login(self.agency_user)
        inbox = self.client.get(reverse('agencyrequests:inbox'), {'status': 'past'})
        self.assertIn(self.future_trip.pk, [b.pk for b in inbox.context['bookings']])
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

    def contacts(self, response, *groups):
        return [b.renter_contact for b in response.context['bookings'] if b.group in groups]

    def test_number_shown_when_renter_allows_it(self):
        UserSettings.objects.filter(user=self.renter_user).update(show_contact_number=True)
        response = self.get_inbox()
        self.assertEqual(self.contacts(response, 'pending'), [self.NUMBER])
        # Both the in-progress and the upcoming trip cards show it.
        self.assertEqual(self.contacts(response, 'upcoming', 'in_progress'), [self.NUMBER, self.NUMBER])
        # Every card carries the renter block now, so the past trip's card shows it too.
        self.assertEqual(self.contacts(response, 'past'), [self.NUMBER])
        self.assertContains(
            response, f'<p class="request-renter-contact">{self.NUMBER}</p>', count=4, html=True
        )

    def test_number_absent_when_renter_hides_it(self):
        UserSettings.objects.filter(user=self.renter_user).update(show_contact_number=False)
        response = self.get_inbox()
        self.assertEqual(self.contacts(response, 'pending'), [''])
        self.assertEqual(self.contacts(response, 'upcoming', 'in_progress'), ['', ''])
        self.assertEqual(self.contacts(response, 'past'), [''])
        self.assertNotContains(response, self.NUMBER)
        self.assertNotContains(response, 'request-renter-contact')

    def test_number_shown_when_renter_has_no_settings_row(self):
        UserSettings.objects.filter(user=self.renter_user).delete()
        response = self.get_inbox()
        self.assertEqual(self.contacts(response, 'pending'), [self.NUMBER])
        self.assertContains(
            response, f'<p class="request-renter-contact">{self.NUMBER}</p>', count=4, html=True
        )
