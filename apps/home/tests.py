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


class SuggestTests(TestCase):
    """dashboard/suggest/: cities for Where, makes and models for What."""

    @classmethod
    def setUpTestData(cls):
        agency_user = User.objects.create_user(
            username='suggest-agency@example.com', email='suggest-agency@example.com',
            password='password123', is_agency=True,
        )
        cls.agency = AgencyProfile.objects.create(
            user=agency_user, business_name='Suggest Rentals', contact_number='0917 000 2222',
        )
        cars = [
            ('Toyota', 'Vios', 'Cebu City', 'available'),
            ('Toyota', 'Innova', 'Cebu City', 'available'),
            ('Honda', 'City', 'Cebu City', 'available'),
            ('Toyota', 'Fortuner', 'Davao City', 'available'),
            ('Toyota', 'Hilux', 'Cebu City', 'maintenance'),   # never counted
            ('Nissan', 'Navara', 'Lapu-Lapu', 'maintenance'),  # its city is never suggested
            ('Suzuki', 'Jimny', 'Talisay', 'unavailable'),     # neither is this one
        ]
        for index, (make, model, city, status) in enumerate(cars):
            cls.make_car(make, model, city, status, f'SUG {index:04d}')

    @classmethod
    def make_car(cls, make, model, city, status, plate):
        return Vehicle.objects.create(
            agency=cls.agency, make=make, model=model, year=2022, plate_number=plate,
            transmission='Automatic', fuel_type='Gasoline', seats=5, color='Silver',
            daily_rate=Decimal('2000.00'), city=city, status=status,
        )

    def suggest(self, field, term):
        response = self.client.get(reverse('home:suggest'), {'field': field, 'term': term})
        self.assertEqual(response.status_code, 200)
        return response.json()['suggestions']

    def test_guests_get_json_that_is_never_cached(self):
        response = self.client.get(reverse('home:suggest'), {'field': 'location', 'term': 'cebu'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_city_results_are_distinct_with_counts_of_available_cars(self):
        self.assertEqual(
            self.suggest('location', 'cebu'),
            [{'value': 'Cebu City', 'label': 'Cebu City', 'meta': '3 cars'}],
        )
        self.assertEqual(
            self.suggest('location', 'davao'),
            [{'value': 'Davao City', 'label': 'Davao City', 'meta': '1 car'}],
        )

    def test_unavailable_cars_cities_are_never_suggested(self):
        self.assertEqual(self.suggest('location', 'lapu'), [])
        self.assertEqual(self.suggest('location', 'talisay'), [])

    def test_city_starting_with_the_term_comes_first(self):
        values = [item['value'] for item in self.suggest('location', 'city')]
        self.assertCountEqual(values, ['Cebu City', 'Davao City'])
        # Neither starts with "city", so the closer match decides; both are present once.
        self.assertEqual(len(values), len(set(values)))
        self.assertEqual([item['value'] for item in self.suggest('location', 'dav')][0], 'Davao City')

    def test_typo_cebo_suggests_cebu_city(self):
        self.assertIn('Cebu City', [item['value'] for item in self.suggest('location', 'cebo')])

    def test_full_city_name_does_not_suggest_other_cities(self):
        self.assertEqual([item['value'] for item in self.suggest('location', 'Cebu City')], ['Cebu City'])
        self.assertEqual([item['value'] for item in self.suggest('location', 'cebu cty')], ['Cebu City'])

    def test_toy_returns_the_make_before_its_models(self):
        items = self.suggest('q', 'toy')
        values = [item['value'] for item in items]
        self.assertEqual(values[0], 'Toyota')
        self.assertEqual(items[0]['meta'], '3 cars')   # the maintenance Hilux doesn't count
        self.assertCountEqual(values[1:], ['Toyota Vios', 'Toyota Innova', 'Toyota Fortuner'])
        self.assertNotIn('Toyota Hilux', values)
        self.assertEqual(items[1]['meta'], '1 car')

    def test_model_term_suggests_only_the_pair(self):
        self.assertEqual(
            self.suggest('q', 'vios'),
            [{'value': 'Toyota Vios', 'label': 'Toyota Vios', 'meta': '1 car'}],
        )

    def test_results_are_capped_at_six(self):
        for index in range(8):
            self.make_car('Kia', f'Model {index}', f'Town {index}', 'available', f'CAP {index:04d}')
        self.assertEqual(len(self.suggest('location', 'town')), 6)
        self.assertEqual(len(self.suggest('q', 'kia')), 6)

    def test_empty_term_or_unknown_field_returns_nothing(self):
        for field, term in (('location', ''), ('location', '   '), ('q', ''), ('city', 'cebu'), ('', 'cebu')):
            with self.subTest(field=field, term=term):
                self.assertEqual(self.suggest(field, term), [])

    def test_post_is_refused(self):
        response = self.client.post(reverse('home:suggest'), {'field': 'location', 'term': 'cebu'})
        self.assertEqual(response.status_code, 405)

    def test_query_count_is_fixed(self):
        with self.assertNumQueries(1):
            self.suggest('location', 'cebu')
        with self.assertNumQueries(2):
            self.suggest('q', 'toy')


class GuestBrowsingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='renter@example.com',
            email='renter@example.com',
            password='password123',
            is_renter=True,
        )
        agency_user = User.objects.create_user(
            username='agency@example.com',
            email='agency@example.com',
            password='password123',
            is_agency=True,
        )
        cls.agency = AgencyProfile.objects.create(
            user=agency_user,
            business_name='Apex Rentals',
            contact_number='0917 000 1111',
        )

    create_vehicle = DashboardViewTests.create_vehicle

    def test_guest_dashboard_hearts_are_login_prompt_links(self):
        vehicle = self.create_vehicle()
        response = self.client.get(reverse('home:dashboard') + '?q=vios')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2022 Toyota Vios')
        self.assertContains(
            response,
            f'<a class="favorite-button" href="{reverse("login:login")}?next=/dashboard/%3Fq%3Dvios" '
            'data-auth-prompt data-auth-icon="save" data-auth-title="Log in to save this car" '
            'aria-label="Log in to save this car">',
        )
        self.assertNotContains(response, 'data-favorite-form')
        self.assertNotContains(response, reverse('fleet:favorite_toggle', args=[vehicle.pk]))

    def test_logged_in_dashboard_keeps_favorite_form(self):
        vehicle = self.create_vehicle()
        self.client.force_login(self.user)
        response = self.client.get(reverse('home:dashboard'))
        self.assertContains(response, 'data-favorite-form')
        self.assertContains(response, f'action="{reverse("fleet:favorite_toggle", args=[vehicle.pk])}"')
        self.assertNotContains(response, 'data-auth-prompt')


class LandingPageTests(TestCase):
    def test_find_your_drive_links_to_dashboard(self):
        response = self.client.get(reverse('home:landing'))
        self.assertContains(response, f'<a class="button" href="{reverse("home:dashboard")}">Find your drive</a>', html=True)
