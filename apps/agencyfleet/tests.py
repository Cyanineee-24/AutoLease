import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AgencyProfile
from apps.bookings.models import Booking
from apps.fleet.models import Vehicle

User = get_user_model()


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
