import datetime
import io
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import AgencyProfile
from apps.bookings.models import Booking
from apps.fleet.models import Vehicle, VehicleImage

User = get_user_model()

TEMP_MEDIA_ROOT = tempfile.mkdtemp(prefix='agencyfleet-tests-')


def png_upload(name='car.png', padding=0):
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(buffer, 'PNG')
    return SimpleUploadedFile(name, buffer.getvalue() + b'\0' * padding, content_type='image/png')


def messages_text(response):
    return ' '.join(str(m) for m in get_messages(response.wsgi_request))


class AgencyFleetTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.agency_user = User.objects.create_user(
            username='agency@example.com',
            email='agency@example.com',
            password='password123',
            is_agency=True,
            first_name='Agency',
        )
        cls.agency_profile = AgencyProfile.objects.create(
            user=cls.agency_user,
            business_name='Cebu City Wheels',
            contact_number='0917 111 2222',
        )

        cls.other_agency_user = User.objects.create_user(
            username='other@example.com',
            email='other@example.com',
            password='password123',
            is_agency=True,
            first_name='Other',
        )
        cls.other_profile = AgencyProfile.objects.create(
            user=cls.other_agency_user,
            business_name='Mandaue Motors',
            contact_number='0917 333 4444',
        )

        cls.renter_user = User.objects.create_user(
            username='renter@example.com',
            email='renter@example.com',
            password='password123',
            is_renter=True,
            first_name='Juan',
        )

        cls.vehicle = cls.make_vehicle(cls.agency_profile, 'ABC 1234')
        cls.other_vehicle = cls.make_vehicle(cls.other_profile, 'ZZZ 9999', make='Honda', model='City')

    @staticmethod
    def make_vehicle(agency, plate, status='available', make='Toyota', model='Vios'):
        return Vehicle.objects.create(
            agency=agency,
            make=make,
            model=model,
            year=2022,
            plate_number=plate,
            transmission='Automatic',
            fuel_type='Gasoline',
            seats=5,
            color='White',
            daily_rate=Decimal('2500.00'),
            city='Cebu City',
            status=status,
        )

    def make_booking(self, vehicle, start_offset, end_offset, status):
        today = timezone.localdate()
        return Booking.objects.create(
            vehicle=vehicle,
            renter=self.renter_user,
            start_date=today + datetime.timedelta(days=start_offset),
            end_date=today + datetime.timedelta(days=end_offset),
            daily_rate_snapshot=vehicle.daily_rate,
            status=status,
        )

    def login_agency(self):
        self.client.force_login(self.agency_user)


class AccessTests(AgencyFleetTestBase):
    def test_anonymous_redirected_to_login(self):
        url = reverse('agencyfleet:list')
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('login:login')}?next={url}", fetch_redirect_response=False)

    def test_renter_redirected_with_agency_error(self):
        self.client.force_login(self.renter_user)
        response = self.client.get(reverse('agencyfleet:list'))
        self.assertRedirects(response, reverse('home:dashboard'), fetch_redirect_response=False)
        self.assertIn('Only rental agencies', messages_text(response))


class ListingsPageTests(AgencyFleetTestBase):
    def test_shows_only_own_cars_including_unavailable_and_maintenance(self):
        self.make_vehicle(self.agency_profile, 'UNA 0001', status='unavailable', make='Nissan', model='Almera')
        self.make_vehicle(self.agency_profile, 'MNT 0002', status='maintenance', make='Suzuki', model='Ertiga')
        self.login_agency()
        response = self.client.get(reverse('agencyfleet:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ABC 1234')
        self.assertContains(response, 'UNA 0001')
        self.assertContains(response, 'MNT 0002')
        self.assertNotContains(response, 'ZZZ 9999')
        self.assertContains(response, '3 cars · 1 available')

    def test_counts_upcoming_and_pending(self):
        self.make_booking(self.vehicle, 3, 5, 'approved')
        self.make_booking(self.vehicle, -10, -8, 'approved')
        self.make_booking(self.vehicle, 10, 12, 'pending')
        self.login_agency()
        response = self.client.get(reverse('agencyfleet:list'))
        self.assertContains(response, '1 upcoming trip<')
        self.assertContains(response, '1 pending request<')

    def test_view_listing_link_only_for_available(self):
        self.vehicle.status = 'maintenance'
        self.vehicle.save()
        self.login_agency()
        response = self.client.get(reverse('agencyfleet:list'))
        self.assertNotContains(response, reverse('fleet:vehicle_detail', args=[self.vehicle.pk]))

    def test_empty_state(self):
        self.client.force_login(self.other_agency_user)
        self.other_vehicle.delete()
        response = self.client.get(reverse('agencyfleet:list'))
        self.assertContains(response, "You haven't listed any cars yet.")


VALID_VEHICLE_DATA = {
    'make': '  Mitsubishi ',
    'model': 'Xpander',
    'year': '2023',
    'plate_number': '  nbc   4567 ',
    'transmission': 'Automatic',
    'fuel_type': 'Gasoline',
    'seats': '7',
    'color': 'Gray',
    'daily_rate': '3500.00',
    'city': 'Lapu-Lapu',
}


class CreateVehicleTests(AgencyFleetTestBase):
    def post_create(self, **overrides):
        self.login_agency()
        return self.client.post(reverse('agencyfleet:create'), {**VALID_VEHICLE_DATA, **overrides})

    def test_get_renders_form(self):
        self.login_agency()
        response = self.client.get(reverse('agencyfleet:create'))
        self.assertContains(response, 'Add a car')

    def test_valid_post_creates_available_car_owned_by_agency(self):
        response = self.post_create()
        vehicle = Vehicle.objects.get(model='Xpander')
        self.assertRedirects(
            response, reverse('agencyfleet:photos', args=[vehicle.pk]), fetch_redirect_response=False,
        )
        self.assertIn('Add photos so renters can see it.', messages_text(response))
        self.assertEqual(vehicle.agency, self.agency_profile)
        self.assertEqual(vehicle.status, 'available')
        self.assertEqual(vehicle.make, 'Mitsubishi')
        self.assertEqual(vehicle.plate_number, 'NBC 4567')

    def test_duplicate_plate_rejected_case_insensitively(self):
        response = self.post_create(plate_number='abc 1234')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Another car already uses this plate number.')
        self.assertFalse(Vehicle.objects.filter(model='Xpander').exists())

    def test_duplicate_plate_of_other_agency_rejected(self):
        response = self.post_create(plate_number='zzz  9999')
        self.assertContains(response, 'Another car already uses this plate number.')

    def test_bounds_rejected(self):
        max_year = timezone.localdate().year + 1
        cases = [
            ({'year': '1989'}, 'year'),
            ({'year': str(max_year + 1)}, 'year'),
            ({'seats': '1'}, 'seats'),
            ({'seats': '16'}, 'seats'),
            ({'daily_rate': '0'}, 'daily_rate'),
            ({'daily_rate': '100000.01'}, 'daily_rate'),
            ({'make': '   '}, 'make'),
            ({'fuel_type': 'Rocket'}, 'fuel_type'),
        ]
        for overrides, field in cases:
            with self.subTest(overrides=overrides):
                response = self.post_create(**overrides)
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context['form'].errors)
        self.assertFalse(Vehicle.objects.filter(model='Xpander').exists())

    def test_upper_bounds_accepted(self):
        max_year = timezone.localdate().year + 1
        response = self.post_create(year=str(max_year), seats='15', daily_rate='100000')
        self.assertEqual(response.status_code, 302)


class EditVehicleTests(AgencyFleetTestBase):
    def test_edit_own_car(self):
        self.login_agency()
        url = reverse('agencyfleet:edit', args=[self.vehicle.pk])
        response = self.client.get(url)
        self.assertContains(response, 'Existing bookings keep the price they were made at.')

        data = {**VALID_VEHICLE_DATA, 'plate_number': 'abc 1234', 'daily_rate': '2999'}
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse('agencyfleet:list'), fetch_redirect_response=False)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.daily_rate, Decimal('2999'))
        self.assertEqual(self.vehicle.plate_number, 'ABC 1234')

    def test_edit_keeps_existing_booking_snapshot(self):
        booking = self.make_booking(self.vehicle, 3, 5, 'approved')
        self.login_agency()
        data = {**VALID_VEHICLE_DATA, 'plate_number': 'ABC 1234', 'daily_rate': '9999'}
        self.client.post(reverse('agencyfleet:edit', args=[self.vehicle.pk]), data)
        booking.refresh_from_db()
        self.assertEqual(booking.daily_rate_snapshot, Decimal('2500.00'))

    def test_legacy_choice_preserved_on_edit(self):
        self.vehicle.transmission = 'CVT'
        self.vehicle.save()
        self.login_agency()
        response = self.client.get(reverse('agencyfleet:edit', args=[self.vehicle.pk]))
        self.assertContains(response, '<option value="CVT" selected>CVT</option>', html=True)

    def test_other_agency_car_404(self):
        self.login_agency()
        url = reverse('agencyfleet:edit', args=[self.other_vehicle.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, VALID_VEHICLE_DATA).status_code, 404)
        self.other_vehicle.refresh_from_db()
        self.assertEqual(self.other_vehicle.model, 'City')


class StatusChangeTests(AgencyFleetTestBase):
    def post_status(self, status, vehicle=None):
        self.login_agency()
        vehicle = vehicle or self.vehicle
        return self.client.post(reverse('agencyfleet:status', args=[vehicle.pk]), {'status': status})

    def test_get_not_allowed(self):
        self.login_agency()
        response = self.client.get(reverse('agencyfleet:status', args=[self.vehicle.pk]))
        self.assertEqual(response.status_code, 405)

    def test_blocked_when_approved_booking_ends_today(self):
        self.make_booking(self.vehicle, -2, 0, 'approved')
        response = self.post_status('maintenance')
        self.assertRedirects(response, reverse('agencyfleet:list'), fetch_redirect_response=False)
        self.assertIn('This car has 1 upcoming trip.', messages_text(response))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, 'available')

    def test_blocked_when_approved_booking_in_future(self):
        self.make_booking(self.vehicle, 5, 7, 'approved')
        self.make_booking(self.vehicle, 10, 12, 'approved')
        response = self.post_status('unavailable')
        self.assertIn('This car has 2 upcoming trips.', messages_text(response))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, 'available')

    def test_allowed_when_only_approved_booking_is_past(self):
        self.make_booking(self.vehicle, -5, -1, 'approved')
        self.post_status('unavailable')
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, 'unavailable')

    def test_allowed_change_declines_future_pending_requests(self):
        future_pending = self.make_booking(self.vehicle, 3, 4, 'pending')
        ongoing_pending = self.make_booking(self.vehicle, -1, 1, 'pending')
        past_pending = self.make_booking(self.vehicle, -9, -8, 'pending')
        other_car_pending = self.make_booking(self.other_vehicle, 3, 4, 'pending')

        response = self.post_status('maintenance')
        self.assertIn('2 pending requests were declined.', messages_text(response))

        for booking in (future_pending, ongoing_pending):
            booking.refresh_from_db()
            self.assertEqual(booking.status, 'declined')
            self.assertEqual(booking.agency_response, 'This car is no longer available.')
            self.assertIsNotNone(booking.decided_at)
        past_pending.refresh_from_db()
        other_car_pending.refresh_from_db()
        self.assertEqual(past_pending.status, 'pending')
        self.assertEqual(other_car_pending.status, 'pending')

    def test_invalid_status_rejected(self):
        response = self.post_status('sold')
        self.assertIn('Choose Available, Unavailable or Maintenance.', messages_text(response))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, 'available')

    def test_back_to_available_always_allowed(self):
        self.vehicle.status = 'maintenance'
        self.vehicle.save()
        self.make_booking(self.vehicle, 5, 7, 'approved')
        self.post_status('available')
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, 'available')

    def test_other_agency_car_404(self):
        response = self.post_status('maintenance', vehicle=self.other_vehicle)
        self.assertEqual(response.status_code, 404)
        self.other_vehicle.refresh_from_db()
        self.assertEqual(self.other_vehicle.status, 'available')


class ApproveUnavailableCarTests(AgencyFleetTestBase):
    def test_approve_refused_when_vehicle_not_available(self):
        booking = self.make_booking(self.vehicle, 3, 5, 'pending')
        self.vehicle.status = 'maintenance'
        self.vehicle.save()
        self.login_agency()
        response = self.client.post(reverse('agencyrequests:decide', args=[booking.pk]), {'action': 'approve'})
        self.assertIn('This car is not available right now.', messages_text(response))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'pending')

    def test_decline_still_works_when_vehicle_not_available(self):
        booking = self.make_booking(self.vehicle, 3, 5, 'pending')
        self.vehicle.status = 'unavailable'
        self.vehicle.save()
        self.login_agency()
        self.client.post(reverse('agencyrequests:decide', args=[booking.pk]), {'action': 'decline'})
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'declined')

    def test_approve_still_works_when_vehicle_available(self):
        booking = self.make_booking(self.vehicle, 3, 5, 'pending')
        self.login_agency()
        self.client.post(reverse('agencyrequests:decide', args=[booking.pk]), {'action': 'approve'})
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'approved')


class DeleteVehicleTests(AgencyFleetTestBase):
    def test_refused_when_any_booking_exists(self):
        for status in ('declined', 'cancelled', 'completed'):
            with self.subTest(status=status):
                Booking.objects.filter(vehicle=self.vehicle).delete()
                self.make_booking(self.vehicle, -9, -8, status)
                self.login_agency()
                response = self.client.post(reverse('agencyfleet:delete', args=[self.vehicle.pk]))
                self.assertIn("Cars with booking history can't be deleted.", messages_text(response))
                self.assertTrue(Vehicle.objects.filter(pk=self.vehicle.pk).exists())

    def test_delete_button_hidden_when_bookings_exist(self):
        self.make_booking(self.vehicle, -9, -8, 'declined')
        self.login_agency()
        response = self.client.get(reverse('agencyfleet:list'))
        self.assertNotContains(response, reverse('agencyfleet:delete', args=[self.vehicle.pk]))

    def test_works_with_no_bookings(self):
        self.login_agency()
        self.assertContains(self.client.get(reverse('agencyfleet:list')), reverse('agencyfleet:delete', args=[self.vehicle.pk]))
        response = self.client.post(reverse('agencyfleet:delete', args=[self.vehicle.pk]))
        self.assertRedirects(response, reverse('agencyfleet:list'), fetch_redirect_response=False)
        self.assertIn('Car deleted.', messages_text(response))
        self.assertFalse(Vehicle.objects.filter(pk=self.vehicle.pk).exists())

    def test_get_not_allowed_and_other_agency_404(self):
        self.login_agency()
        self.assertEqual(self.client.get(reverse('agencyfleet:delete', args=[self.vehicle.pk])).status_code, 405)
        response = self.client.post(reverse('agencyfleet:delete', args=[self.other_vehicle.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Vehicle.objects.filter(pk=self.other_vehicle.pk).exists())


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class PhotoTests(AgencyFleetTestBase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.login_agency()
        self.photos_url = reverse('agencyfleet:photos', args=[self.vehicle.pk])

    def upload(self, upload=None, vehicle=None):
        url = reverse('agencyfleet:photos', args=[vehicle.pk]) if vehicle else self.photos_url
        return self.client.post(url, {'image': upload or png_upload()})

    def test_page_renders(self):
        response = self.client.get(self.photos_url)
        self.assertContains(response, '0 of 10 photos')
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_first_upload_becomes_primary_second_does_not(self):
        self.assertRedirects(self.upload(), self.photos_url, fetch_redirect_response=False)
        self.upload()
        first, second = VehicleImage.objects.filter(vehicle=self.vehicle).order_by('id')
        self.assertTrue(first.is_primary)
        self.assertFalse(second.is_primary)
        self.assertEqual(second.sort_order, first.sort_order + 1)
        self.assertTrue(first.image.name.startswith('fleet/vehicles/'))
        self.assertTrue(default_storage.exists(first.image.name))

    def test_set_primary_leaves_exactly_one(self):
        self.upload()
        self.upload()
        self.upload()
        target = VehicleImage.objects.filter(vehicle=self.vehicle).order_by('id').last()
        response = self.client.post(reverse('agencyfleet:photo_primary', args=[self.vehicle.pk, target.pk]))
        self.assertRedirects(response, self.photos_url, fetch_redirect_response=False)
        primaries = VehicleImage.objects.filter(vehicle=self.vehicle, is_primary=True)
        self.assertEqual(list(primaries), [target])

    def test_deleting_primary_promotes_next_and_removes_file(self):
        self.upload()
        self.upload()
        self.upload()
        first, second, third = VehicleImage.objects.filter(vehicle=self.vehicle).order_by('id')
        self.client.post(reverse('agencyfleet:photo_delete', args=[self.vehicle.pk, first.pk]))
        self.assertFalse(VehicleImage.objects.filter(pk=first.pk).exists())
        self.assertFalse(default_storage.exists(first.image.name))
        second.refresh_from_db()
        third.refresh_from_db()
        self.assertTrue(second.is_primary)
        self.assertFalse(third.is_primary)

    def test_eleventh_upload_refused(self):
        for _ in range(10):
            self.upload()
        response = self.client.get(self.photos_url)
        self.assertNotContains(response, 'type="file"')
        self.assertContains(response, 'the most allowed')

        response = self.upload()
        self.assertIn('up to 10 photos', messages_text(response))
        self.assertEqual(VehicleImage.objects.filter(vehicle=self.vehicle).count(), 10)

    def test_non_image_file_rejected(self):
        fake = SimpleUploadedFile('car.png', b'definitely not an image', content_type='image/png')
        response = self.upload(fake)
        self.assertEqual(response.status_code, 200)
        self.assertIn('image', response.context['form'].errors)
        self.assertFalse(VehicleImage.objects.filter(vehicle=self.vehicle).exists())

    def test_wrong_extension_and_oversize_rejected(self):
        for upload, message in (
            (png_upload('car.gif'), 'Use a JPG, PNG or WebP image.'),
            (png_upload(padding=5 * 1024 * 1024), 'Photos must be 5 MB or smaller.'),
        ):
            with self.subTest(message=message):
                response = self.upload(upload)
                self.assertContains(response, message)
        self.assertFalse(VehicleImage.objects.filter(vehicle=self.vehicle).exists())

    def test_other_agency_car_and_image_404(self):
        self.assertEqual(self.client.get(reverse('agencyfleet:photos', args=[self.other_vehicle.pk])).status_code, 404)
        self.assertEqual(self.upload(vehicle=self.other_vehicle).status_code, 404)

        other_image = VehicleImage.objects.create(vehicle=self.other_vehicle, image=png_upload(), is_primary=True)
        self.upload()
        own_image = VehicleImage.objects.get(vehicle=self.vehicle)
        urls = [
            # Other agency's car and image.
            reverse('agencyfleet:photo_primary', args=[self.other_vehicle.pk, other_image.pk]),
            reverse('agencyfleet:photo_delete', args=[self.other_vehicle.pk, other_image.pk]),
            # Own car, but an image belonging to another car.
            reverse('agencyfleet:photo_primary', args=[self.vehicle.pk, other_image.pk]),
            reverse('agencyfleet:photo_delete', args=[self.vehicle.pk, other_image.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(VehicleImage.objects.filter(pk=other_image.pk, is_primary=True).exists())
        own_image.refresh_from_db()
        self.assertTrue(own_image.is_primary)

    def test_deleting_car_removes_photo_files(self):
        self.upload()
        name = VehicleImage.objects.get(vehicle=self.vehicle).image.name
        self.client.post(reverse('agencyfleet:delete', args=[self.vehicle.pk]))
        self.assertFalse(Vehicle.objects.filter(pk=self.vehicle.pk).exists())
        self.assertFalse(default_storage.exists(name))

    def test_list_shows_photo_count_and_image(self):
        self.upload()
        response = self.client.get(reverse('agencyfleet:list'))
        self.assertContains(response, 'Photos (1)')
        self.assertContains(response, 'class="listing-image"')
