import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import AgencyProfile
from apps.bookings.models import Booking, Review
from apps.fleet.models import Vehicle
from apps.usersettings.models import UserSettings

User = get_user_model()


class Command(BaseCommand):
    help = (
        'Idempotently seeds demo users, agency, 14 vehicles, completed bookings, '
        'reviews, and one future approved booking for testing/demo purposes.\n'
        'Usage: python manage.py seed_fleet'
    )

    def handle(self, *args, **options):
        self.stdout.write('Seeding fleet data...')

        # 1. Agency user
        agency_user, created = User.objects.get_or_create(
            email='demo-agency@example.com',
            defaults={
                'username': 'demo-agency@example.com',
                'contact_number': '0917 123 4567',
                'is_agency': True,
                'first_name': 'Demo',
                'last_name': 'Agency',
            },
        )
        agency_user.set_password('password123')
        agency_user.is_agency = True
        agency_user.save()

        agency_profile, _ = AgencyProfile.objects.get_or_create(
            user=agency_user,
            defaults={
                'business_name': 'Demo Rentals',
                'contact_number': '0917 123 4567',
            },
        )

        settings_row, _ = UserSettings.objects.get_or_create(
            user=agency_user,
            defaults={'show_contact_number': True},
        )
        settings_row.show_contact_number = True
        settings_row.save()

        # 2. Renter users
        renters_data = [
            ('demo-renter@example.com', 'Maria', 'Santos'),
            ('demo-renter2@example.com', 'Paolo', 'Reyes'),
            ('demo-renter3@example.com', 'Ana', 'Cruz'),
        ]
        renters = []
        for email, first_name, last_name in renters_data:
            u, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    'username': email,
                    'is_renter': True,
                    'first_name': first_name,
                    'last_name': last_name,
                    'contact_number': '0918 000 0001',
                },
            )
            u.set_password('password123')
            u.is_renter = True
            u.first_name = first_name
            u.last_name = last_name
            u.save()
            renters.append(u)

        # 3. 14 Vehicles across specified cities
        vehicles_specs = [
            # 1: Top rated (3 reviews @ 5.0)
            {
                'plate_number': 'CAE 1001',
                'make': 'Toyota',
                'model': 'Vios',
                'year': 2022,
                'transmission': 'Automatic',
                'fuel_type': 'Gasoline',
                'seats': 5,
                'color': 'White',
                'daily_rate': Decimal('2500.00'),
                'city': 'Cebu City',
            },
            # 2: Top rated (3 reviews @ 5.0)
            {
                'plate_number': 'CAE 1002',
                'make': 'Honda',
                'model': 'City',
                'year': 2021,
                'transmission': 'Automatic',
                'fuel_type': 'Gasoline',
                'seats': 5,
                'color': 'Modern Steel',
                'daily_rate': Decimal('2800.00'),
                'city': 'Mandaue',
            },
            # 3: Top rated (4 reviews @ 5.0)
            {
                'plate_number': 'CAE 1003',
                'make': 'Mitsubishi',
                'model': 'Xpander',
                'year': 2023,
                'transmission': 'Automatic',
                'fuel_type': 'Gasoline',
                'seats': 7,
                'color': 'Graphite Gray',
                'daily_rate': Decimal('3500.00'),
                'city': 'Lapu-Lapu',
            },
            # 4: 2 reviews @ 5.0 -> Not top rated (needs >= 3)
            {
                'plate_number': 'CAE 1004',
                'make': 'Suzuki',
                'model': 'Ertiga',
                'year': 2020,
                'transmission': 'Manual',
                'fuel_type': 'Gasoline',
                'seats': 7,
                'color': 'Burgundy Red',
                'daily_rate': Decimal('2600.00'),
                'city': 'Talisay',
            },
            # 5: 1 review @ 5.0 -> Not top rated
            {
                'plate_number': 'CAE 1005',
                'make': 'Nissan',
                'model': 'Almera',
                'year': 2019,
                'transmission': 'Manual',
                'fuel_type': 'Gasoline',
                'seats': 5,
                'color': 'Brilliant Silver',
                'daily_rate': Decimal('1800.00'),
                'city': 'Cebu City',
            },
            # 6: 3 reviews @ 4.0 -> Not top rated (needs >= 4.8)
            {
                'plate_number': 'CAE 1006',
                'make': 'Hyundai',
                'model': 'Accent',
                'year': 2021,
                'transmission': 'Automatic',
                'fuel_type': 'Diesel',
                'seats': 5,
                'color': 'Phantom Black',
                'daily_rate': Decimal('2200.00'),
                'city': 'Davao City',
            },
            # 7: 3 reviews @ ~4.33 -> Not top rated
            {
                'plate_number': 'CAE 1007',
                'make': 'Toyota',
                'model': 'Innova',
                'year': 2024,
                'transmission': 'Automatic',
                'fuel_type': 'Diesel',
                'seats': 7,
                'color': 'Silver Metallic',
                'daily_rate': Decimal('4200.00'),
                'city': 'Cebu City',
            },
            # 8: 0 reviews -> "New"
            {
                'plate_number': 'CAE 1008',
                'make': 'Toyota',
                'model': 'Fortuner',
                'year': 2023,
                'transmission': 'Automatic',
                'fuel_type': 'Diesel',
                'seats': 7,
                'color': 'Attitude Black',
                'daily_rate': Decimal('5500.00'),
                'city': 'Mandaue',
            },
            # 9: 0 reviews -> "New"
            {
                'plate_number': 'CAE 1009',
                'make': 'Honda',
                'model': 'BR-V',
                'year': 2022,
                'transmission': 'Automatic',
                'fuel_type': 'Gasoline',
                'seats': 7,
                'color': 'Taffeta White',
                'daily_rate': Decimal('3200.00'),
                'city': 'Davao City',
            },
            # 10: 0 reviews -> "New"
            {
                'plate_number': 'CAE 1010',
                'make': 'Mitsubishi',
                'model': 'Mirage G4',
                'year': 2018,
                'transmission': 'Manual',
                'fuel_type': 'Gasoline',
                'seats': 5,
                'color': 'Wine Red',
                'daily_rate': Decimal('1500.00'),
                'city': 'Talisay',
            },
            # 11: 0 reviews -> "New"
            {
                'plate_number': 'CAE 1011',
                'make': 'Nissan',
                'model': 'Navara',
                'year': 2022,
                'transmission': 'Automatic',
                'fuel_type': 'Diesel',
                'seats': 5,
                'color': 'Galaxy Black',
                'daily_rate': Decimal('4800.00'),
                'city': 'Lapu-Lapu',
            },
            # 12: 0 reviews -> "New"
            {
                'plate_number': 'CAE 1012',
                'make': 'Suzuki',
                'model': 'Jimny',
                'year': 2023,
                'transmission': 'Automatic',
                'fuel_type': 'Gasoline',
                'seats': 5,
                'color': 'Kinetic Yellow',
                'daily_rate': Decimal('3800.00'),
                'city': 'Cebu City',
            },
            # 13: 0 reviews -> "New"
            {
                'plate_number': 'CAE 1013',
                'make': 'Hyundai',
                'model': 'Stargazer',
                'year': 2024,
                'transmission': 'Automatic',
                'fuel_type': 'Gasoline',
                'seats': 7,
                'color': 'Magnetic Silver',
                'daily_rate': Decimal('3600.00'),
                'city': 'Mandaue',
            },
            # 14: 0 reviews -> "New"
            {
                'plate_number': 'CAE 1014',
                'make': 'Toyota',
                'model': 'Hilux',
                'year': 2023,
                'transmission': 'Manual',
                'fuel_type': 'Diesel',
                'seats': 5,
                'color': 'Super White',
                'daily_rate': Decimal('4500.00'),
                'city': 'Davao City',
            },
        ]

        created_vehicles = []
        for spec in vehicles_specs:
            plate = spec['plate_number']
            v, _ = Vehicle.objects.get_or_create(
                plate_number=plate,
                defaults={
                    'agency': agency_profile,
                    'make': spec['make'],
                    'model': spec['model'],
                    'year': spec['year'],
                    'transmission': spec['transmission'],
                    'fuel_type': spec['fuel_type'],
                    'seats': spec['seats'],
                    'color': spec['color'],
                    'daily_rate': spec['daily_rate'],
                    'city': spec['city'],
                    'status': 'available',
                },
            )
            created_vehicles.append(v)

        # 4. Past Bookings & Reviews
        # Vehicle 1: 3 reviews @ 5.0 (Maria, Paolo, Ana)
        reviews_plan = [
            (
                created_vehicles[0],
                [
                    (renters[0], datetime.date(2024, 1, 10), datetime.date(2024, 1, 13), 5, 'Clean car, smooth pick-up. Would rent again.'),
                    (renters[1], datetime.date(2024, 1, 15), datetime.date(2024, 1, 18), 5, 'Great for our family trip to Moalboal.'),
                    (renters[2], datetime.date(2024, 1, 20), datetime.date(2024, 1, 22), 5, 'Fuel efficient and very reliable.'),
                ],
            ),
            (
                created_vehicles[1],
                [
                    (renters[0], datetime.date(2024, 2, 1), datetime.date(2024, 2, 4), 5, 'Super smooth transmission and nice cold AC.'),
                    (renters[1], datetime.date(2024, 2, 6), datetime.date(2024, 2, 8), 5, 'Excellent host and on-time turnover.'),
                    (renters[2], datetime.date(2024, 2, 12), datetime.date(2024, 2, 15), 5, 'Immaculate condition. Highly recommended!'),
                ],
            ),
            (
                created_vehicles[2],
                [
                    (renters[0], datetime.date(2024, 3, 1), datetime.date(2024, 3, 4), 5, 'Spacious 7-seater, plenty of luggage room.'),
                    (renters[1], datetime.date(2024, 3, 8), datetime.date(2024, 3, 11), 5, 'Great comfort for island driving.'),
                    (renters[2], datetime.date(2024, 3, 15), datetime.date(2024, 3, 18), 5, 'Easy booking and quick inspection.'),
                    (renters[0], datetime.date(2024, 3, 22), datetime.date(2024, 3, 25), 5, 'Drove smoothly up the hills in Busay.'),
                ],
            ),
            (
                created_vehicles[3],
                [
                    (renters[0], datetime.date(2024, 4, 1), datetime.date(2024, 4, 3), 5, 'Good family car, responsive host.'),
                    (renters[1], datetime.date(2024, 4, 5), datetime.date(2024, 4, 7), 5, 'Comfortable ride.'),
                ],
            ),
            (
                created_vehicles[4],
                [
                    (renters[0], datetime.date(2024, 4, 10), datetime.date(2024, 4, 12), 5, 'Affordable and clean.'),
                ],
            ),
            (
                created_vehicles[5],
                [
                    (renters[0], datetime.date(2024, 5, 1), datetime.date(2024, 5, 3), 4, 'Good diesel mileage, decent condition.'),
                    (renters[1], datetime.date(2024, 5, 5), datetime.date(2024, 5, 7), 4, 'Gets the job done.'),
                    (renters[2], datetime.date(2024, 5, 10), datetime.date(2024, 5, 12), 4, 'Acceptable ride for the price.'),
                ],
            ),
            (
                created_vehicles[6],
                [
                    (renters[0], datetime.date(2024, 6, 1), datetime.date(2024, 6, 4), 4, 'Solid van, minor scratch on bumper.'),
                    (renters[1], datetime.date(2024, 6, 8), datetime.date(2024, 6, 11), 5, 'Powerful engine and clean interior.'),
                    (renters[2], datetime.date(2024, 6, 15), datetime.date(2024, 6, 18), 4, 'Very comfortable for 7 people.'),
                ],
            ),
        ]

        for vehicle, b_list in reviews_plan:
            for renter_user, s_date, e_date, rating, comment in b_list:
                booking, _ = Booking.objects.get_or_create(
                    vehicle=vehicle,
                    start_date=s_date,
                    end_date=e_date,
                    defaults={
                        'renter': renter_user,
                        'daily_rate_snapshot': vehicle.daily_rate,
                        'status': 'completed',
                        'renter_message': 'Looking forward to the trip!',
                    },
                )
                Review.objects.get_or_create(
                    booking=booking,
                    defaults={
                        'rating': rating,
                        'comment': comment,
                    },
                )

        # 5. One approved FUTURE booking on one vehicle
        demo_future_vehicle = created_vehicles[0]
        future_start = datetime.date(2026, 11, 10)
        future_end = datetime.date(2026, 11, 15)

        future_booking, _ = Booking.objects.get_or_create(
            vehicle=demo_future_vehicle,
            start_date=future_start,
            end_date=future_end,
            defaults={
                'renter': renters[0],
                'daily_rate_snapshot': demo_future_vehicle.daily_rate,
                'status': 'approved',
                'renter_message': 'Upcoming business trip in Cebu.',
            },
        )
        if future_booking.status != 'approved':
            future_booking.status = 'approved'
            future_booking.save()

        self.stdout.write(self.style.SUCCESS('Successfully seeded fleet data.'))
        self.stdout.write('----------------------------------------------------')
        self.stdout.write('Credentials:')
        self.stdout.write('  Agency: demo-agency@example.com / password123')
        self.stdout.write('  Renter 1: demo-renter@example.com / password123')
        self.stdout.write('  Renter 2: demo-renter2@example.com / password123')
        self.stdout.write('  Renter 3: demo-renter3@example.com / password123')
        self.stdout.write('----------------------------------------------------')
        self.stdout.write(
            f'Demo Future Booking (searching these dates hides this vehicle):\n'
            f'  Plate: {demo_future_vehicle.plate_number}\n'
            f'  Vehicle: {demo_future_vehicle.year} {demo_future_vehicle.make} {demo_future_vehicle.model}\n'
            f'  Dates: {future_start} to {future_end}\n'
        )
