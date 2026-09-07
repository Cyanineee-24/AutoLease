from django.test import TestCase
from django.urls import reverse

from .models import AgencyProfile, CustomUser


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
            reverse('accounts:register'),
            self.registration_data(),
            follow=True,
        )

        self.assertRedirects(response, reverse('accounts:login'))
        user = CustomUser.objects.get(email='renter@example.com')
        self.assertTrue(user.is_renter)
        self.assertFalse(user.is_agency)
        self.assertEqual(user.username, user.email)
        # assertRedirects followed the redirect to login, where credentials were popped and rendered
        self.assertContains(response, 'value="renter@example.com"')
        self.assertContains(response, 'value="A-secure-password-123"')
        self.assertContains(response, 'Account created successfully! Click Log in to continue.')


    def test_agency_registration_creates_an_agency_profile(self):
        response = self.client.post(
            reverse('accounts:register'),
            self.registration_data(
                email='agency@example.com',
                account_type='agency',
                business_name='City Drives',
                contact_number='09171234567',
            ),
        )

        self.assertRedirects(response, reverse('accounts:login'))
        user = CustomUser.objects.get(email='agency@example.com')
        profile = AgencyProfile.objects.get(user=user)
        self.assertTrue(user.is_agency)
        self.assertEqual(user.contact_number, '09171234567')
        self.assertEqual(profile.business_name, 'City Drives')
        self.assertEqual(profile.contact_number, '09171234567')

    def test_renter_registration_saves_contact_number(self):
        response = self.client.post(
            reverse('accounts:register'),
            self.registration_data(contact_number='09189876543'),
        )

        self.assertRedirects(response, reverse('accounts:login'))
        user = CustomUser.objects.get(email='renter@example.com')
        self.assertEqual(user.contact_number, '09189876543')

    def test_agency_registration_requires_business_details(self):
        response = self.client.post(
            reverse('accounts:register'),
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
            reverse('accounts:login'),
            {
                'username': 'user@example.com',
                'password': 'A-secure-password-123',
            },
        )
        self.assertRedirects(response, reverse('accounts:renter_dashboard'))

    def test_login_renders_prefilled_credentials_and_clears_session(self):
        session = self.client.session
        session['prefill_email'] = 'prefill@example.com'
        session['prefill_password'] = 'prefill-pass'
        session.save()

        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="prefill@example.com"')
        self.assertContains(response, 'value="prefill-pass"')
        self.assertNotIn('prefill_email', self.client.session)
        self.assertNotIn('prefill_password', self.client.session)

