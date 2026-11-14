from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import AgencyProfile, CustomUser


class RegistrationViewTests(TestCase):
    def registration_data(self, **overrides):
        data = {
            'email': 'renter@example.com',
            'account_type': 'renter',
            'business_name': '',
            'contact_number': '',
            'password1': 'A-secure-password-123',
            'password2': 'A-secure-password-123',
        }
        data.update(overrides)
        return data

    def test_renter_registration_creates_a_renter_account(self):
        response = self.client.post(
            reverse('register:register'),
            self.registration_data(),
            follow=True,
        )

        self.assertRedirects(response, reverse('login:login'))
        user = CustomUser.objects.get(email='renter@example.com')
        self.assertTrue(user.is_renter)
        self.assertFalse(user.is_agency)
        self.assertEqual(user.username, user.email)
        # assertRedirects followed the redirect to login, where email was popped and rendered
        self.assertContains(response, 'value="renter@example.com"')
        self.assertContains(response, 'Account created successfully! Click Log in to continue.')

    def test_agency_registration_creates_an_agency_profile(self):
        response = self.client.post(
            reverse('register:register'),
            self.registration_data(
                email='agency@example.com',
                account_type='agency',
                business_name='City Drives',
                contact_number='09171234567',
            ),
        )

        self.assertRedirects(response, reverse('login:login'))
        user = CustomUser.objects.get(email='agency@example.com')
        profile = AgencyProfile.objects.get(user=user)
        self.assertTrue(user.is_agency)
        self.assertEqual(user.contact_number, '09171234567')
        self.assertEqual(profile.business_name, 'City Drives')
        self.assertEqual(profile.contact_number, '09171234567')

    def test_renter_registration_saves_contact_number(self):
        response = self.client.post(
            reverse('register:register'),
            self.registration_data(contact_number='09189876543'),
        )

        self.assertRedirects(response, reverse('login:login'))
        user = CustomUser.objects.get(email='renter@example.com')
        self.assertEqual(user.contact_number, '09189876543')

    def test_safe_next_is_kept_and_forwarded_to_login(self):
        url = reverse('register:register') + '?next=/vehicles/1/'
        self.assertContains(self.client.get(url), '<input type="hidden" name="next" value="/vehicles/1/">', html=True)

        response = self.client.post(url, self.registration_data())
        self.assertRedirects(response, '/login/?next=%2Fvehicles%2F1%2F', fetch_redirect_response=False)
        self.assertTrue(CustomUser.objects.filter(email='renter@example.com').exists())

    def test_next_from_post_body_is_used(self):
        response = self.client.post(
            reverse('register:register'),
            self.registration_data(next='/vehicles/1/?start_date=2030-01-01&end_date=2030-01-03'),
        )
        self.assertRedirects(
            response,
            '/login/?next=%2Fvehicles%2F1%2F%3Fstart_date%3D2030-01-01%26end_date%3D2030-01-03',
            fetch_redirect_response=False,
        )

    def test_offsite_next_is_ignored(self):
        url = reverse('register:register') + '?next=https://evil.com'
        self.assertNotContains(self.client.get(url), 'evil.com')
        response = self.client.post(url, self.registration_data())
        self.assertRedirects(response, reverse('login:login'), fetch_redirect_response=False)

    def test_agency_registration_requires_business_details(self):
        response = self.client.post(
            reverse('register:register'),
            self.registration_data(account_type='agency'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CustomUser.objects.exists())
        self.assertContains(response, 'Enter your business name.')


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='user@example.com',
            email='user@example.com',
            password='A-secure-password-123',
        )

    def test_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse('login:login'),
            {
                'username': 'user@example.com',
                'password': 'A-secure-password-123',
            },
        )
        self.assertRedirects(response, reverse('home:dashboard'))

    def test_login_renders_prefilled_email_and_clears_session(self):
        session = self.client.session
        session['prefill_email'] = 'prefill@example.com'
        session.save()

        response = self.client.get(reverse('login:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="prefill@example.com"')
        self.assertContains(
            response,
            '<input type="password" name="password" id="id_password" autocomplete="current-password" required>',
        )
        self.assertNotContains(response, 'id="id_password" autocomplete="current-password" required value')
        self.assertNotIn('prefill_email', self.client.session)

    def test_login_redirects_to_valid_next(self):
        response = self.client.post(
            reverse('login:login'),
            {
                'username': 'user@example.com',
                'password': 'A-secure-password-123',
                'next': '/vehicles/1/?start_date=2030-01-01&end_date=2030-01-03',
            },
        )
        self.assertRedirects(
            response,
            '/vehicles/1/?start_date=2030-01-01&end_date=2030-01-03',
            fetch_redirect_response=False,
        )

    def test_login_ignores_offsite_next(self):
        response = self.client.post(
            reverse('login:login'),
            {
                'username': 'user@example.com',
                'password': 'A-secure-password-123',
                'next': 'https://evil.com/',
            },
        )
        self.assertRedirects(response, reverse('home:dashboard'))
