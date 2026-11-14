import importlib

from django.apps import apps as django_apps
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.usersettings.models import UserSettings

backfill_module = importlib.import_module('apps.usersettings.migrations.0003_backfill_usersettings')


class AutoCreatedSettingsTests(TestCase):
    def test_create_user_creates_exactly_one_settings_row_with_defaults(self):
        user = CustomUser.objects.create_user(username='a@example.com', email='a@example.com', password='pw-123456')
        rows = UserSettings.objects.filter(user=user)
        self.assertEqual(rows.count(), 1)
        row = rows.get()
        self.assertTrue(row.email_notifications)
        self.assertTrue(row.marketing_emails)
        self.assertFalse(row.sms_notifications)
        self.assertTrue(row.show_contact_number)

    def test_saving_existing_user_does_not_duplicate(self):
        user = CustomUser.objects.create_user(username='b@example.com', email='b@example.com', password='pw-123456')
        user.first_name = 'Bea'
        user.save()
        self.assertEqual(UserSettings.objects.filter(user=user).count(), 1)

    def test_registration_creates_settings_for_renter_and_agency(self):
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
                self.assertEqual(UserSettings.objects.filter(user=user).count(), 1)

    def test_settings_page_uses_the_existing_row(self):
        user = CustomUser.objects.create_user(username='c@example.com', email='c@example.com', password='pw-123456')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('usersettings:settings')).status_code, 200)
        self.assertEqual(UserSettings.objects.filter(user=user).count(), 1)


class BackfillUserSettingsMigrationTests(TestCase):
    def test_backfill_creates_missing_rows_and_is_idempotent(self):
        with_row = CustomUser.objects.create_user(username='keep@example.com', email='keep@example.com', password='pw-123456')
        UserSettings.objects.filter(user=with_row).update(show_contact_number=False)
        missing = [
            CustomUser.objects.create_user(username=f'm{i}@example.com', email=f'm{i}@example.com', password='pw-123456')
            for i in range(3)
        ]
        # Simulate users created before the signal existed.
        UserSettings.objects.filter(user__in=missing).delete()

        backfill_module.backfill_usersettings(django_apps, None)
        backfill_module.backfill_usersettings(django_apps, None)

        for user in [with_row, *missing]:
            self.assertEqual(UserSettings.objects.filter(user=user).count(), 1)
        new_row = UserSettings.objects.get(user=missing[0])
        self.assertTrue(new_row.email_notifications)
        self.assertTrue(new_row.marketing_emails)
        self.assertFalse(new_row.sms_notifications)
        self.assertTrue(new_row.show_contact_number)
        # Existing rows are left alone.
        self.assertFalse(UserSettings.objects.get(user=with_row).show_contact_number)
