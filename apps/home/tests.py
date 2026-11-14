from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import AgencyProfile
from apps.fleet.models import Vehicle

User = get_user_model()


class DashboardAccessTests(TestCase):
    def test_dashboard_open_to_guests(self):
        """GET /dashboard/ unauthenticated renders the browse page."""
        response = self.client.get(reverse('home:dashboard'))
        self.assertEqual(response.status_code, 200)


class DashboardViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='renter@example.com',
            email='renter@example.com',
            password='password123',
            is_renter=True,
        )
        cls.agency_user = User.objects.create_user(
            username='agency@example.com',
            email='agency@example.com',
            password='password123',
            is_agency=True,
        )
        cls.agency = AgencyProfile.objects.create(
            user=cls.agency_user,
            business_name='Apex Rentals',
            contact_number='0917 000 1111',
        )

    def create_vehicle(self, make='Toyota', model='Vios', plate='PLT 001', city='Cebu City', status='available'):
        return Vehicle.objects.create(
            agency=self.agency,
            make=make,
            model=model,
            year=2022,
            plate_number=plate,
            transmission='Automatic',
            fuel_type='Gasoline',
            seats=5,
            color='Silver',
            daily_rate=Decimal('2000.00'),
            city=city,
            status=status,
        )

    def test_dashboard_singular_and_plural_count_text(self):
        self.client.force_login(self.user)

        # 1 vehicle -> "1 car available"
        self.create_vehicle(plate='PLT 101')
        resp = self.client.get(reverse('home:dashboard'))
        self.assertContains(resp, '1 car available')
        self.assertNotContains(resp, '1 cars available')

        # 2 vehicles -> "2 cars available"
        self.create_vehicle(plate='PLT 102')
        resp2 = self.client.get(reverse('home:dashboard'))
        self.assertContains(resp2, '2 cars available')

    def test_empty_states_render_appropriately(self):
        self.client.force_login(self.user)

        # (a) No vehicles in system: "No cars available yet"
        resp_empty = self.client.get(reverse('home:dashboard'))
        self.assertContains(resp_empty, 'No cars available yet')
        self.assertContains(
            resp_empty,
            'Check back soon — rental agencies are getting their vehicles ready to list on AutoLease.',
        )
        self.assertNotContains(resp_empty, 'No cars match your search')
        self.assertNotContains(resp_empty, 'Clear search')

        # (b) Vehicles exist, but search yields 0 results: "No cars match your search"
        self.create_vehicle(make='Toyota', model='Vios', plate='PLT 201', city='Cebu City')
        resp_no_match = self.client.get(reverse('home:dashboard'), {'q': 'Ferrari'})
        self.assertContains(resp_no_match, 'No cars match your search')
        self.assertContains(resp_no_match, 'Try a different make, city, or dates.')
        self.assertContains(resp_no_match, 'Clear search')
        self.assertNotContains(resp_no_match, 'No cars available yet')

    def test_pagination_and_query_preservation(self):
        self.client.force_login(self.user)
        # Create 13 vehicles
        for i in range(13):
            self.create_vehicle(make='Toyota', model=f'Model-{i}', plate=f'PAG {i:03d}')

        # Page 1 has 12 vehicles
        resp_p1 = self.client.get(reverse('home:dashboard'), {'q': 'Toyota'})
        self.assertEqual(len(resp_p1.context['page_obj']), 12)
        self.assertContains(resp_p1, 'Page 1 of 2')
        self.assertContains(resp_p1, 'href="?q=Toyota&page=2"')

        # Page 2 has 1 vehicle
        resp_p2 = self.client.get(reverse('home:dashboard'), {'q': 'Toyota', 'page': 2})
        self.assertEqual(len(resp_p2.context['page_obj']), 1)
        self.assertContains(resp_p2, 'Page 2 of 2')
        self.assertContains(resp_p2, 'href="?q=Toyota&page=1"')

    def test_end_before_start_shows_error_and_returns_results(self):
        self.client.force_login(self.user)
        self.create_vehicle(make='Honda', model='City', plate='ERR 001')

        # Drop-off before pick-up
        resp = self.client.get(
            reverse('home:dashboard'),
            {'start_date': '2026-10-20', 'end_date': '2026-10-15'},
        )
        self.assertContains(resp, 'Drop-off must be on or after pick-up.')
        self.assertContains(resp, 'Honda')

    def test_search_inputs_repopulated_from_get(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse('home:dashboard'),
            {
                'location': 'Mandaue',
                'q': 'civic',
                'start_date': '2026-10-20',
                'end_date': '2026-10-25',
            },
        )
        self.assertContains(resp, 'value="Mandaue"')
        self.assertContains(resp, 'value="civic"')
        self.assertContains(resp, 'value="2026-10-20"')
        self.assertContains(resp, 'value="2026-10-25"')
