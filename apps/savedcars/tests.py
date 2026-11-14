import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AgencyProfile
from apps.fleet.models import Favorite, Vehicle
from apps.usersettings.models import UserSettings

User = get_user_model()


class SavedCarsTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.agency_user = User.objects.create_user(
            username='agency@example.com',
            email='agency@example.com',
            password='password123',
            is_agency=True,
            first_name='Agency',
            last_name='Owner',
        )
        cls.agency_profile = AgencyProfile.objects.create(
            user=cls.agency_user,
            business_name='Cebu City Wheels',
            contact_number='0917 111 2222',
        )
        cls.agency_settings = UserSettings.objects.create(
            user=cls.agency_user,
            show_contact_number=True,
        )

        cls.renter_user = User.objects.create_user(
            username='renter@example.com',
            email='renter@example.com',
            password='password123',
            is_renter=True,
            first_name='Juan',
            last_name='Dela Cruz',
        )
        cls.other_renter = User.objects.create_user(
            username='renter2@example.com',
            email='renter2@example.com',
            password='password123',
            is_renter=True,
            first_name='Ana',
            last_name='Cruz',
        )

        cls.vios = cls.make_vehicle('ABC 1234', 'Toyota', 'Vios')
        cls.city = cls.make_vehicle('DEF 5678', 'Honda', 'City')
        cls.almera = cls.make_vehicle('GHI 9012', 'Nissan', 'Almera', status='maintenance')

    @classmethod
    def make_vehicle(cls, plate, make, model, status='available'):
        return Vehicle.objects.create(
            agency=cls.agency_profile,
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

    def save_car(self, user, vehicle, minutes_ago):
        favorite = Favorite.objects.create(user=user, vehicle=vehicle)
        # created_at is auto_now_add, so set the ordering timestamp explicitly.
        Favorite.objects.filter(pk=favorite.pk).update(
            created_at=timezone.now() - datetime.timedelta(minutes=minutes_ago),
        )
        return favorite


class SavedListTests(SavedCarsTestBase):
    url = reverse('savedcars:list')

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login:login')}?next={self.url}", fetch_redirect_response=False)

    def test_empty_state(self):
        self.client.force_login(self.renter_user)
        response = self.client.get(self.url)
        self.assertContains(response, 'No saved cars yet. Tap the heart on any car to save it here.')
        self.assertContains(response, f'href="{reverse("home:dashboard")}">Browse cars</a>')
        self.assertContains(response, '0 saved cars')

    def test_shows_only_own_saved_cars_newest_first(self):
        self.save_car(self.renter_user, self.vios, minutes_ago=30)
        self.save_car(self.renter_user, self.city, minutes_ago=5)
        self.save_car(self.other_renter, self.almera, minutes_ago=1)
        self.client.force_login(self.renter_user)
        response = self.client.get(self.url)

        self.assertEqual(response.context['available'], [self.city, self.vios])
        self.assertEqual(response.context['unavailable'], [])
        self.assertContains(response, '2 saved cars')
        self.assertNotContains(response, 'Nissan Almera')
        self.assertNotContains(response, 'No longer available')
        # Hearts on this page show as saved.
        self.assertContains(response, 'class="favorite-button is-saved"', count=2)

    def test_singular_subtitle(self):
        self.save_car(self.renter_user, self.vios, minutes_ago=1)
        self.client.force_login(self.renter_user)
        self.assertContains(self.client.get(self.url), '1 saved car<')

    def test_unavailable_car_listed_separately_without_detail_link(self):
        self.save_car(self.renter_user, self.vios, minutes_ago=10)
        self.save_car(self.renter_user, self.almera, minutes_ago=1)
        self.client.force_login(self.renter_user)
        response = self.client.get(self.url)

        self.assertEqual(response.context['available'], [self.vios])
        self.assertEqual(response.context['unavailable'], [self.almera])
        self.assertContains(response, 'No longer available')
        self.assertContains(response, 'Not available right now')
        self.assertContains(response, '2022 Nissan Almera')
        # The Remove form posts to /vehicles/<pk>/favorite/, so match the href exactly.
        self.assertNotContains(response, f'href="{reverse("fleet:vehicle_detail", args=[self.almera.pk])}"')
        self.assertContains(response, f'href="{reverse("fleet:vehicle_detail", args=[self.vios.pk])}"')
        self.assertContains(response, f'action="{reverse("fleet:favorite_toggle", args=[self.almera.pk])}"')
        self.assertContains(response, 'data-favorite-form', count=1)

    def test_no_n_plus_one(self):
        self.client.force_login(self.renter_user)
        self.save_car(self.renter_user, self.vios, minutes_ago=1)
        with self.assertNumQueries(4):
            # session + user, the vehicle query, the images prefetch
            self.client.get(self.url)
        self.save_car(self.renter_user, self.city, minutes_ago=2)
        self.save_car(self.renter_user, self.almera, minutes_ago=3)
        with self.assertNumQueries(4):
            self.client.get(self.url)


class RemoveSavedCarTests(SavedCarsTestBase):
    def test_remove_unavailable_car_from_saved_page(self):
        self.save_car(self.renter_user, self.almera, minutes_ago=1)
        self.client.force_login(self.renter_user)
        saved_url = reverse('savedcars:list')
        response = self.client.post(
            reverse('fleet:favorite_toggle', args=[self.almera.pk]),
            {'next': saved_url},
        )
        self.assertRedirects(response, saved_url, fetch_redirect_response=False)
        self.assertFalse(Favorite.objects.filter(user=self.renter_user, vehicle=self.almera).exists())

    def test_saving_unavailable_car_returns_404(self):
        self.client.force_login(self.renter_user)
        response = self.client.post(reverse('fleet:favorite_toggle', args=[self.almera.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Favorite.objects.filter(user=self.renter_user, vehicle=self.almera).exists())

    def test_unsaving_unavailable_car_via_xhr(self):
        self.save_car(self.renter_user, self.almera, minutes_ago=1)
        self.client.force_login(self.renter_user)
        response = self.client.post(
            reverse('fleet:favorite_toggle', args=[self.almera.pk]),
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response.json(), {'favorited': False})
        self.assertFalse(Favorite.objects.filter(user=self.renter_user, vehicle=self.almera).exists())

    def test_unknown_vehicle_returns_404(self):
        self.client.force_login(self.renter_user)
        response = self.client.post(reverse('fleet:favorite_toggle', args=[999999]))
        self.assertEqual(response.status_code, 404)


class SavedNavTests(SavedCarsTestBase):
    def test_nav_shows_saved_for_logged_in_users(self):
        for user in (self.renter_user, self.agency_user):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                response = self.client.get(reverse('home:dashboard'))
                self.assertContains(response, f'href="{reverse("savedcars:list")}"')
                self.assertContains(response, '<span class="dropdown-label">Saved</span>', html=True)

    def test_nav_hides_saved_for_guests(self):
        response = self.client.get(reverse('home:landing'))
        self.assertNotContains(response, reverse('savedcars:list'))
