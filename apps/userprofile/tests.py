import importlib
import io
import shutil
import tempfile

from django.apps import apps as django_apps
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts.models import AgencyProfile, CustomUser
from apps.userprofile.models import Profile

backfill_profiles_module = importlib.import_module('apps.userprofile.migrations.0003_backfill_profiles')
TEMP_MEDIA_ROOT = tempfile.mkdtemp(prefix='userprofile-tests-')


def png_upload(name='me.png', padding=0):
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), 'blue').save(buffer, 'PNG')
    return SimpleUploadedFile(name, buffer.getvalue() + b'\0' * padding, content_type='image/png')


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


class AutoCreatedProfileTests(TestCase):
    def test_create_user_creates_exactly_one_profile(self):
        user = CustomUser.objects.create_user(username='a@example.com', email='a@example.com', password='pw-123456')
        self.assertEqual(Profile.objects.filter(user=user).count(), 1)
        user.last_name = 'Again'
        user.save()
        self.assertEqual(Profile.objects.filter(user=user).count(), 1)

    def test_registration_creates_profile_for_renter_and_agency(self):
        for email, account_type, business in (
            ('renter@example.com', 'renter', ''),
            ('agency@example.com', 'agency', 'Cebu Wheels'),
        ):
            with self.subTest(account_type=account_type):
                self.client.post(reverse('register:register'), {
                    'email': email,
                    'account_type': account_type,
                    'business_name': business,
                    'contact_number': '0917 000 0000',
                    'password1': 'A-secure-password-123',
                    'password2': 'A-secure-password-123',
                })
                user = CustomUser.objects.get(email=email)
                self.assertEqual(Profile.objects.filter(user=user).count(), 1)

    def test_backfill_creates_missing_profiles_and_is_idempotent(self):
        kept = CustomUser.objects.create_user(username='keep@example.com', email='keep@example.com', password='pw-123456')
        Profile.objects.filter(user=kept).update(bio='Keep me')
        missing = [
            CustomUser.objects.create_user(username=f'm{i}@example.com', email=f'm{i}@example.com', password='pw-123456')
            for i in range(3)
        ]
        # Simulate users created before the signal existed.
        Profile.objects.filter(user__in=missing).delete()

        backfill_profiles_module.backfill_profiles(django_apps, None)
        backfill_profiles_module.backfill_profiles(django_apps, None)

        for user in [kept, *missing]:
            self.assertEqual(Profile.objects.filter(user=user).count(), 1)
        self.assertEqual(Profile.objects.get(user=kept).bio, 'Keep me')

    def test_pages_do_not_crash_without_profile_row(self):
        user = CustomUser.objects.create_user(username='n@example.com', email='n@example.com', password='pw-123456', first_name='Nora')
        Profile.objects.filter(user=user).delete()
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse('home:dashboard')), '<span class="avatar-circle">N</span>', html=True)
        self.assertEqual(self.client.get(reverse('userprofile:profile')).status_code, 200)
        self.assertEqual(self.client.get(reverse('userprofile:profile_edit')).status_code, 200)
        self.assertTrue(Profile.objects.filter(user=user).exists())


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class ProfileBioAndPhotoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(
            username='photo@example.com',
            email='photo@example.com',
            password='pw-123456',
            is_renter=True,
            first_name='Pia',
            last_name='Reyes',
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.client.force_login(self.user)
        self.edit_url = reverse('userprofile:profile_edit')

    def post_edit(self, **extra):
        data = {'first_name': 'Pia', 'last_name': 'Reyes', 'contact_number': '', 'profile-bio': ''}
        data.update(extra)
        return self.client.post(self.edit_url, data)

    def profile(self):
        return Profile.objects.get(user=self.user)

    def test_edit_page_is_multipart_with_bio_and_photo_fields(self):
        response = self.client.get(self.edit_url)
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="profile-bio"')
        self.assertContains(response, 'name="profile-profile_image"')
        self.assertContains(response, 'Max 500 characters.')

    def test_saving_bio_shows_on_profile_page(self):
        response = self.post_edit(**{'profile-bio': 'Weekend driver.\nLoves road trips.'})
        self.assertRedirects(response, reverse('userprofile:profile'), fetch_redirect_response=False)
        self.assertEqual(self.profile().bio, 'Weekend driver.\nLoves road trips.')
        page = self.client.get(reverse('userprofile:profile'))
        self.assertContains(page, '<p class="profile-bio">Weekend driver.<br>Loves road trips.</p>', html=True)

    def test_bio_over_500_characters_rejected(self):
        response = self.post_edit(**{'profile-bio': 'x' * 501, 'first_name': 'Changed'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Keep your bio to 500 characters or fewer.')
        self.assertEqual(self.profile().bio, '')
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Pia')  # nothing saved when any form is invalid

    def test_no_photo_shows_initial(self):
        profile_page = self.client.get(reverse('userprofile:profile'))
        self.assertContains(profile_page, '<div class="profile-avatar">P</div>', html=True)
        self.assertNotContains(profile_page, 'alt="Profile photo"')
        nav = self.client.get(reverse('home:dashboard'))
        self.assertContains(nav, '<span class="avatar-circle">P</span>', html=True)

    def test_upload_photo_shows_on_profile_and_nav(self):
        response = self.post_edit(**{'profile-profile_image': png_upload()})
        self.assertRedirects(response, reverse('userprofile:profile'), fetch_redirect_response=False)
        image = self.profile().profile_image
        self.assertTrue(image.name.startswith('userprofile/'))
        self.assertTrue(default_storage.exists(image.name))

        profile_page = self.client.get(reverse('userprofile:profile'))
        self.assertContains(profile_page, f'<img src="{image.url}" alt="Profile photo">', html=True)
        nav = self.client.get(reverse('home:dashboard'))
        self.assertContains(nav, 'class="avatar-circle avatar-circle--photo"')
        self.assertContains(nav, f'<img src="{image.url}" alt="Profile photo">', html=True)

    def test_wrong_type_and_oversize_rejected(self):
        for upload, message in (
            (png_upload('me.gif'), 'Use a JPG, PNG or WebP image.'),
            (png_upload(padding=2 * 1024 * 1024), 'Profile photos must be 2 MB or smaller.'),
        ):
            with self.subTest(message=message):
                response = self.post_edit(**{'profile-profile_image': upload})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.assertFalse(self.profile().profile_image)

    def test_replacing_photo_deletes_old_file(self):
        self.post_edit(**{'profile-profile_image': png_upload('first.png')})
        old_name = self.profile().profile_image.name
        self.post_edit(**{'profile-profile_image': png_upload('second.png')})
        new_name = self.profile().profile_image.name
        self.assertNotEqual(old_name, new_name)
        self.assertFalse(default_storage.exists(old_name))
        self.assertTrue(default_storage.exists(new_name))

    def test_clear_removes_photo_and_deletes_file(self):
        self.post_edit(**{'profile-profile_image': png_upload()})
        old_name = self.profile().profile_image.name
        self.assertContains(self.client.get(self.edit_url), 'name="profile-profile_image-clear"')

        response = self.post_edit(**{'profile-profile_image-clear': 'on'})
        self.assertRedirects(response, reverse('userprofile:profile'), fetch_redirect_response=False)
        self.assertFalse(self.profile().profile_image)
        self.assertFalse(default_storage.exists(old_name))
        nav = self.client.get(reverse('home:dashboard'))
        self.assertContains(nav, '<span class="avatar-circle">P</span>', html=True)

    def test_saving_other_fields_keeps_photo(self):
        self.post_edit(**{'profile-profile_image': png_upload()})
        name = self.profile().profile_image.name
        self.post_edit(**{'profile-bio': 'Hello'})
        self.assertEqual(self.profile().profile_image.name, name)
        self.assertTrue(default_storage.exists(name))
