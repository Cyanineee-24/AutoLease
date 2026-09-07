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
        )

        self.assertRedirects(response, reverse('accounts:renter_dashboard'))
        user = CustomUser.objects.get(email='renter@example.com')
        self.assertTrue(user.is_renter)
        self.assertFalse(user.is_agency)
        self.assertEqual(user.username, user.email)

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

        self.assertRedirects(response, reverse('home'))
        user = CustomUser.objects.get(email='agency@example.com')
        profile = AgencyProfile.objects.get(user=user)
        self.assertTrue(user.is_agency)
        self.assertEqual(profile.business_name, 'City Drives')

    def test_agency_registration_requires_business_details(self):
        response = self.client.post(
            reverse('accounts:register'),
            self.registration_data(account_type='agency'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CustomUser.objects.exists())
        self.assertContains(response, 'Enter your business name.')
