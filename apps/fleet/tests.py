import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import AgencyProfile
from apps.bookings.models import Booking, Review
from apps.fleet.models import Favorite, Vehicle
from apps.usersettings.models import UserSettings

User = get_user_model()


class FleetTestBase(TestCase):
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

        cls.vehicle = Vehicle.objects.create(
            agency=cls.agency_profile,
            make='Toyota',
            model='Vios',
            year=2022,
            plate_number='ABC 1234',
            transmission='Automatic',
            fuel_type='Gasoline',
            seats=5,
            color='White',
            daily_rate=Decimal('2500.00'),
            city='Cebu City',
            status='available',
        )


class VehicleQuerySetSearchTests(FleetTestBase):
    def test_search_by_make_model_and_multi_word(self):
        # Match make
        res_make = list(Vehicle.objects.available().search(q='Toyota'))
        self.assertIn(self.vehicle, res_make)

        # Match model
        res_model = list(Vehicle.objects.available().search(q='Vios'))
        self.assertIn(self.vehicle, res_model)

        # Multi-word match
        res_multi = list(Vehicle.objects.available().search(q='toyota vios'))
        self.assertIn(self.vehicle, res_multi)

    def test_search_typo_tolerance(self):
        # "toyta" finds "Toyota" via trigram similarity
        res_typo = list(Vehicle.objects.available().search(q='toyta'))
        self.assertIn(self.vehicle, res_typo)

    def test_search_location_and_location_typo(self):
        # Exact/case-insensitive location
        res_loc = list(Vehicle.objects.available().search(location='Cebu City'))
        self.assertIn(self.vehicle, res_loc)

        # Location typo tolerance
        res_loc_typo = list(Vehicle.objects.available().search(location='cebu cty'))
        self.assertIn(self.vehicle, res_loc_typo)

    def test_status_filtering_excludes_unavailable_and_maintenance(self):
        unavail = Vehicle.objects.create(
            agency=self.agency_profile,
            make='Honda',
            model='City',
            year=2021,
            plate_number='UNAV 001',
            transmission='Automatic',
            fuel_type='Gasoline',
            seats=5,
            color='Silver',
            daily_rate=Decimal('2500.00'),
            city='Cebu City',
            status='unavailable',
        )
        maint = Vehicle.objects.create(
            agency=self.agency_profile,
            make='Nissan',
            model='Almera',
            year=2020,
            plate_number='MAIN 001',
            transmission='Manual',
            fuel_type='Gasoline',
            seats=5,
            color='Black',
            daily_rate=Decimal('1800.00'),
            city='Cebu City',
            status='maintenance',
        )

        results = list(Vehicle.objects.available().search())
        self.assertNotIn(unavail, results)
        self.assertNotIn(maint, results)


class VehicleDateExclusionTests(FleetTestBase):
    def setUp(self):
        super().setUp()
        self.booking_start = datetime.date(2026, 10, 10)
        self.booking_end = datetime.date(2026, 10, 15)
        self.booking = Booking.objects.create(
            renter=self.renter_user,
            vehicle=self.vehicle,
            start_date=self.booking_start,
            end_date=self.booking_end,
            daily_rate_snapshot=self.vehicle.daily_rate,
            status='approved',
        )

    def test_approved_overlapping_booking_hides_vehicle(self):
        # Search fully inside booking
        res = list(
            Vehicle.objects.available().search(
                start=datetime.date(2026, 10, 11),
                end=datetime.date(2026, 10, 14),
            )
        )
        self.assertNotIn(self.vehicle, res)

    def test_inclusive_boundary_overlap_hides_vehicle(self):
        # Search starts on the day the booking ends
        res = list(
            Vehicle.objects.available().search(
                start=datetime.date(2026, 10, 15),
                end=datetime.date(2026, 10, 18),
            )
        )
        self.assertNotIn(self.vehicle, res)

        # Search ends on the day the booking starts
        res2 = list(
            Vehicle.objects.available().search(
                start=datetime.date(2026, 10, 5),
                end=datetime.date(2026, 10, 10),
            )
        )
        self.assertNotIn(self.vehicle, res2)

    def test_non_overlapping_booking_does_not_hide_vehicle(self):
        res = list(
            Vehicle.objects.available().search(
                start=datetime.date(2026, 10, 16),
                end=datetime.date(2026, 10, 20),
            )
        )
        self.assertIn(self.vehicle, res)

    def test_non_approved_statuses_do_not_hide_vehicle(self):
        for status in ['pending', 'declined', 'cancelled', 'completed']:
            self.booking.status = status
            self.booking.save()
            res = list(
                Vehicle.objects.available().search(
                    start=datetime.date(2026, 10, 11),
                    end=datetime.date(2026, 10, 14),
                )
            )
            self.assertIn(self.vehicle, res)

    def test_dates_ignored_when_end_before_start(self):
        # start > end -> dates ignored, vehicle remains visible
        res = list(
            Vehicle.objects.available().search(
                start=datetime.date(2026, 10, 14),
                end=datetime.date(2026, 10, 11),
            )
        )
        self.assertIn(self.vehicle, res)


class VehicleRatingsAndTopRatedTests(FleetTestBase):
    def test_ratings_annotations_and_top_rated_boundaries(self):
        # Initially, 0 reviews
        v = Vehicle.objects.available().with_ratings().get(pk=self.vehicle.pk)
        self.assertEqual(v.review_count, 0)
        self.assertIsNone(v.avg_rating)
        self.assertFalse(v.is_top_rated)

        # Create 2 reviews with 5.0 rating -> count 2, avg 5.0 -> is_top_rated False (< 3 reviews)
        b1 = Booking.objects.create(
            renter=self.renter_user,
            vehicle=self.vehicle,
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 1, 3),
            daily_rate_snapshot=self.vehicle.daily_rate,
            status='completed',
        )
        Review.objects.create(booking=b1, rating=5)

        b2 = Booking.objects.create(
            renter=self.renter_user,
            vehicle=self.vehicle,
            start_date=datetime.date(2024, 1, 5),
            end_date=datetime.date(2024, 1, 7),
            daily_rate_snapshot=self.vehicle.daily_rate,
            status='completed',
        )
        Review.objects.create(booking=b2, rating=5)

        v = Vehicle.objects.available().with_ratings().get(pk=self.vehicle.pk)
        self.assertEqual(v.review_count, 2)
        self.assertEqual(v.avg_rating, 5.0)
        self.assertFalse(v.is_top_rated)

        # Add 3rd review with 5 -> count 3, avg 5.0 >= 4.8 -> is_top_rated True
        b3 = Booking.objects.create(
            renter=self.renter_user,
            vehicle=self.vehicle,
            start_date=datetime.date(2024, 1, 10),
            end_date=datetime.date(2024, 1, 12),
            daily_rate_snapshot=self.vehicle.daily_rate,
            status='completed',
        )
        Review.objects.create(booking=b3, rating=5)

        v = Vehicle.objects.available().with_ratings().get(pk=self.vehicle.pk)
        self.assertEqual(v.review_count, 3)
        self.assertEqual(v.avg_rating, 5.0)
        self.assertTrue(v.is_top_rated)

        # Add 2 more reviews with rating 4 -> ratings (5, 5, 5, 4, 4) -> sum 23 / 5 = 4.6 (< 4.8) -> False
        b4 = Booking.objects.create(
            renter=self.renter_user,
            vehicle=self.vehicle,
            start_date=datetime.date(2024, 1, 15),
            end_date=datetime.date(2024, 1, 17),
            daily_rate_snapshot=self.vehicle.daily_rate,
            status='completed',
        )
        Review.objects.create(booking=b4, rating=4)

        b5 = Booking.objects.create(
            renter=self.renter_user,
            vehicle=self.vehicle,
            start_date=datetime.date(2024, 1, 20),
            end_date=datetime.date(2024, 1, 22),
            daily_rate_snapshot=self.vehicle.daily_rate,
            status='completed',
        )
        Review.objects.create(booking=b5, rating=4)

        v = Vehicle.objects.available().with_ratings().get(pk=self.vehicle.pk)
        self.assertEqual(v.review_count, 5)
        self.assertAlmostEqual(float(v.avg_rating), 4.6, places=2)
        self.assertFalse(v.is_top_rated)


class VehiclePriceDisplayTests(FleetTestBase):
    def test_price_formatting_in_card(self):
        # 2500.00 renders "2,500"
        tpl = Template("{% include 'fleet/_vehicle_card.html' with vehicle=vehicle %}")
        rendered = tpl.render(Context({'vehicle': self.vehicle, 'request': None}))
        self.assertIn('₱2,500', rendered)
        self.assertNotIn('₱2,500.00', rendered)

        # 2500.50 renders "2,500.50"
        self.vehicle.daily_rate = Decimal('2500.50')
        self.vehicle.save()
        rendered_cents = tpl.render(Context({'vehicle': self.vehicle, 'request': None}))
        self.assertIn('₱2,500.50', rendered_cents)


class VehicleDetailViewTests(FleetTestBase):
    def test_login_required(self):
        url = reverse('fleet:vehicle_detail', args=[self.vehicle.pk])
        response = self.client.get(url)
        self.assertRedirects(response, f'/login/?next={url}', fetch_redirect_response=False)

    def test_status_200_for_available_and_404_for_unavailable_or_maintenance(self):
        self.client.force_login(self.renter_user)
        url = reverse('fleet:vehicle_detail', args=[self.vehicle.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Unavailable -> 404
        self.vehicle.status = 'unavailable'
        self.vehicle.save()
        self.assertEqual(self.client.get(url).status_code, 404)

        # Maintenance -> 404
        self.vehicle.status = 'maintenance'
        self.vehicle.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_contact_number_visibility(self):
        self.client.force_login(self.renter_user)
        url = reverse('fleet:vehicle_detail', args=[self.vehicle.pk])

        # 1. By default with show_contact_number=True
        response = self.client.get(url)
        self.assertContains(response, '0917 111 2222')

        # 2. Hidden when show_contact_number=False
        self.agency_settings.show_contact_number = False
        self.agency_settings.save()
        response_hidden = self.client.get(url)
        self.assertNotContains(response_hidden, '0917 111 2222')

        # 3. Shown when owner has no UserSettings row (treat None as True)
        self.agency_settings.delete()
        response_no_row = self.client.get(url)
        self.assertContains(response_no_row, '0917 111 2222')

    def test_plate_number_absent_from_html(self):
        self.client.force_login(self.renter_user)
        url = reverse('fleet:vehicle_detail', args=[self.vehicle.pk])
        response = self.client.get(url)
        self.assertNotContains(response, self.vehicle.plate_number)

    def test_reviewer_display_name_and_no_email_leaks(self):
        # Create a booking with review by a user with no first_name
        nameless_renter = User.objects.create_user(
            username='secret-user@example.com',
            email='secret-user@example.com',
            password='password123',
            is_renter=True,
            first_name='',
        )
        b = Booking.objects.create(
            renter=nameless_renter,
            vehicle=self.vehicle,
            start_date=datetime.date(2024, 2, 1),
            end_date=datetime.date(2024, 2, 3),
            daily_rate_snapshot=self.vehicle.daily_rate,
            status='completed',
        )
        Review.objects.create(booking=b, rating=5, comment='Nice car!')

        self.client.force_login(self.renter_user)
        url = reverse('fleet:vehicle_detail', args=[self.vehicle.pk])
        response = self.client.get(url)
        self.assertContains(response, 'Renter')
        self.assertNotContains(response, 'secret-user@example.com')

    def test_dates_prefill_and_back_link_preserves_query(self):
        self.client.force_login(self.renter_user)
        url = reverse('fleet:vehicle_detail', args=[self.vehicle.pk])
        query = '?q=vios&location=Cebu&start_date=2026-10-15&end_date=2026-10-18'
        response = self.client.get(url + query)

        self.assertContains(response, 'value="2026-10-15"')
        self.assertContains(response, 'value="2026-10-18"')
        self.assertContains(response, 'data-rate="2500.00"')
        self.assertContains(response, 'href="/dashboard/?q=vios&amp;location=Cebu&amp;start_date=2026-10-15&amp;end_date=2026-10-18"')


class FavoriteToggleTests(FleetTestBase):
    def test_login_required(self):
        url = reverse('fleet:favorite_toggle', args=[self.vehicle.pk])
        response = self.client.post(url)
        self.assertRedirects(response, f'/login/?next={url}', fetch_redirect_response=False)

    def test_get_returns_405(self):
        self.client.force_login(self.renter_user)
        url = reverse('fleet:favorite_toggle', args=[self.vehicle.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_post_creates_then_deletes_favorite(self):
        self.client.force_login(self.renter_user)
        url = reverse('fleet:favorite_toggle', args=[self.vehicle.pk])

        # 1st POST creates
        self.client.post(url)
        self.assertTrue(
            Favorite.objects.filter(user=self.renter_user, vehicle=self.vehicle).exists()
        )

        # 2nd POST deletes
        self.client.post(url)
        self.assertFalse(
            Favorite.objects.filter(user=self.renter_user, vehicle=self.vehicle).exists()
        )

    def test_xhr_post_returns_json(self):
        self.client.force_login(self.renter_user)
        url = reverse('fleet:favorite_toggle', args=[self.vehicle.pk])

        # 1st XHR: favorited True
        resp1 = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.json(), {'favorited': True})

        # 2nd XHR: favorited False
        resp2 = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json(), {'favorited': False})

    def test_non_xhr_post_redirects(self):
        self.client.force_login(self.renter_user)
        url = reverse('fleet:favorite_toggle', args=[self.vehicle.pk])
        resp = self.client.post(url, {'next': '/dashboard/'})
        self.assertRedirects(resp, '/dashboard/')

    def test_dashboard_renders_aria_pressed_for_favorited_car(self):
        Favorite.objects.create(user=self.renter_user, vehicle=self.vehicle)
        self.client.force_login(self.renter_user)
        resp = self.client.get(reverse('home:dashboard'))
        self.assertContains(resp, 'aria-pressed="true"')


class SeedFleetCommandTests(TestCase):
    def test_seed_fleet_idempotent_and_creates_14_vehicles(self):
        # Call command twice
        call_command('seed_fleet')
        self.assertEqual(Vehicle.objects.count(), 14)

        call_command('seed_fleet')
        self.assertEqual(Vehicle.objects.count(), 14)

        # At least 3 vehicles are top rated
        top_rated_count = sum(
            1 for v in Vehicle.objects.available().with_ratings() if v.is_top_rated
        )
        self.assertGreaterEqual(top_rated_count, 3)
