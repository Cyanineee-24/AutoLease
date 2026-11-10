from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import AgencyProfile, CustomUser


class ProfileEditViewTests(TestCase):
    """Tests for the profile_edit view."""

    @classmethod
    def setUpTestData(cls):
        cls.renter = CustomUser.objects.create_user(
            username='renter@test.com',
            email='renter@test.com',
            password='testpass123',
            is_renter=True,
            first_name='Jane',
            last_name='Doe',
            contact_number='09171234567',
        )
        cls.agency_user = CustomUser.objects.create_user(
            username='agency@test.com',
            email='agency@test.com',
            password='testpass123',
            is_agency=True,
            first_name='Agency',
            last_name='Owner',
            contact_number='09179876543',
        )
        cls.agency_profile = AgencyProfile.objects.create(
            user=cls.agency_user,
            business_name='Test Motors',
            contact_number='09170000000',
        )

    def test_profile_edit_requires_login(self):
        """GET /profile/edit/ without authentication → redirect."""
        response = self.client.get(reverse('userprofile:profile_edit'))
        self.assertRedirects(response, '/login/?next=/profile/edit/', fetch_redirect_response=False)

    def test_profile_edit_get_renders_form(self):
        """Authenticated GET → 200 with form fields."""
        self.client.login(username='renter@test.com', password='testpass123')
        response = self.client.get(reverse('userprofile:profile_edit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'first_name')
        self.assertContains(response, 'last_name')
        self.assertContains(response, 'contact_number')

    def test_profile_edit_post_updates_user(self):
        """POST with valid data updates CustomUser fields and redirects."""
        self.client.login(username='renter@test.com', password='testpass123')
        response = self.client.post(
            reverse('userprofile:profile_edit'),
            {
                'first_name': 'Janet',
                'last_name': 'Smith',
                'contact_number': '09181111111',
            },
        )
        self.assertRedirects(response, reverse('userprofile:profile'))

        self.renter.refresh_from_db()
        self.assertEqual(self.renter.first_name, 'Janet')
        self.assertEqual(self.renter.last_name, 'Smith')
        self.assertEqual(self.renter.contact_number, '09181111111')

    def test_profile_edit_agency_updates(self):
        """Agency user POST updates both CustomUser and AgencyProfile."""
        self.client.login(username='agency@test.com', password='testpass123')
        response = self.client.post(
            reverse('userprofile:profile_edit'),
            {
                'first_name': 'NewFirst',
                'last_name': 'NewLast',
                'contact_number': '09182222222',
                # AgencyEditForm uses prefix='agency'
                'agency-business_name': 'Updated Motors',
                'agency-contact_number': '09183333333',
            },
        )
        self.assertRedirects(response, reverse('userprofile:profile'))

        self.agency_user.refresh_from_db()
        self.assertEqual(self.agency_user.first_name, 'NewFirst')
        self.assertEqual(self.agency_user.last_name, 'NewLast')
        self.assertEqual(self.agency_user.contact_number, '09182222222')

        self.agency_profile.refresh_from_db()
        self.assertEqual(self.agency_profile.business_name, 'Updated Motors')
        self.assertEqual(self.agency_profile.contact_number, '09183333333')

    def test_agency_user_without_agency_profile_renders_profile_edit(self):
        """is_agency=True user WITHOUT an AgencyProfile row gets 200 on profile_edit (no agency form rendered, no crash)."""
        CustomUser.objects.create_user(
            username='agency_noprofile@test.com',
            email='agency_noprofile@test.com',
            password='testpass123',
            is_agency=True,
            first_name='Agency',
            last_name='NoProfile',
        )
        self.client.login(username='agency_noprofile@test.com', password='testpass123')
        response = self.client.get(reverse('userprofile:profile_edit'))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['agency_form'])
        self.assertNotContains(response, 'Business details')


class ProfileViewTests(TestCase):
    """Tests for the profile read-only view."""

    def test_agency_user_without_agency_profile_renders_profile(self):
        """is_agency=True user WITHOUT an AgencyProfile row gets 200 on profile (no agency details rendered, no crash)."""
        CustomUser.objects.create_user(
            username='agency_noprofile@test.com',
            email='agency_noprofile@test.com',
            password='testpass123',
            is_agency=True,
            first_name='Agency',
            last_name='NoProfile',
        )
        self.client.login(username='agency_noprofile@test.com', password='testpass123')
        response = self.client.get(reverse('userprofile:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('agency_profile', response.context)
        self.assertNotContains(response, 'Agency details')
