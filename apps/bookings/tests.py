from django.test import TestCase
from django.urls import reverse


class GuestBookingRequestTests(TestCase):
    def test_guest_post_redirects_to_login(self):
        url = reverse('bookings:request', args=[1])
        response = self.client.post(url, {'start_date': '2030-01-01', 'end_date': '2030-01-03'})
        self.assertRedirects(response, f"{reverse('login:login')}?next={url}", fetch_redirect_response=False)
