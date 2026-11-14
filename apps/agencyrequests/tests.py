from django.urls import reverse

from apps.mybookings.tests import BookingStatusTestBase


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
