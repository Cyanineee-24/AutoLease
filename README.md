# AutoLease

AutoLease is a car rental platform that connects renters with local rental agencies. Agencies list their cars; renters browse, pick dates and send a booking request, which the agency approves or declines. There are no online payments: a booking is an agreement between the renter and the agency. AutoLease is a CSIT327 final project built with Django's Model-View-Template (MVT) pattern.

## Features

### Guests (not logged in)
- Browse and search available cars: typo-tolerant search by make or model and by city, plus a pick-up/drop-off date filter that hides cars already booked on those dates.
- Car pages with photos, specs, the agency's name and reviews.
- When a guest tries to save a car, request a booking or see an agency's contact details, a login prompt opens. After logging in or signing up they return to the same page, with their chosen dates kept.

### Renters
- Register and log in.
- Profile with name, contact number, bio and profile photo (shown in the navigation bar).
- Driver's license upload, required before requesting a car.
- Request a car for a date range with an optional message to the agency. The daily rate is fixed at request time.
- My bookings: every request with its status. Approved trips show Upcoming, In progress or Completed based on their dates. Pending requests can be cancelled at any time, and approved trips until the day before pick-up.
- Leave one review (1 to 5 stars and a comment) after a trip has ended. It appears on the car page with the renter's first name only.
- Saved cars: heart a car to save it. Saved cars that become unavailable can still be removed.
- Settings: email notifications on or off, and password change. The "Show contact number" toggle currently has no effect for renters: agencies always see a renter's contact number on their booking requests.

### Agencies
- My listings: add and edit cars, set their status (Available, Unavailable or Maintenance), upload up to 10 photos per car and choose the main photo, and delete cars that have no booking history.
  - A car can't be taken off the road while it has upcoming or in-progress trips. Taking it off declines its pending requests.
- Booking requests:
  - Approve or decline pending requests with an optional reply. Approving a request automatically declines other pending requests for the same car on overlapping dates.
  - An Upcoming trips section where trips that haven't started can be cancelled with a reason the renter sees.
  - A history of past decisions.
- Settings: choose whether the agency's contact number is shown on its car pages.

### Notifications
Booking events send an email: a new request to the agency, an approval or decline to the renter, and a cancellation to the other side. Each user's "Email notifications" setting is respected. In development the emails are printed to the console (see "Emails in development"). The Marketing emails and SMS toggles on the settings page are saved, but nothing sends those messages yet.

### Accounts
An account is either a renter or an agency, chosen at sign-up. An agency account also has a business profile (business name and contact number).

## Tech stack

- Python 3.12 or newer, Django 6.1.1
- PostgreSQL hosted on Supabase, accessed with psycopg 3.3.5
  - `pg_trgm` trigram similarity for typo-tolerant make, model and city search
  - A generated full-text search vector on make, model and city
  - An exclusion constraint (needs `btree_gist`) that stops two approved bookings of the same car from overlapping
- Vanilla HTML, CSS and JavaScript (no frontend framework)
- Pillow 12.3.0 for image uploads, python-dotenv 1.2.3 for the `.env` file

## Project structure

The project uses vertical slicing: each feature is its own Django app under `apps/`, and owns its views, URLs, forms, `templates/<app>/` and `static/css/<app>/` (plus `static/js/<app>/` where it needs JavaScript). Models live in the app whose domain they belong to and are imported by the feature apps that use them.

| App | Responsibility |
|---|---|
| `accounts` | Shared model layer: `CustomUser` (renter or agency) and `AgencyProfile`, plus the `agency_required` decorator |
| `register` | Sign-up for renters and agencies |
| `login` | Log in and log out, and the login prompt modal shown to guests |
| `home` | Landing page and the browse/search dashboard |
| `fleet` | `Vehicle`, `VehicleImage` and `Favorite` models, search queries, the car detail page, saving a car, and the `seed_fleet` command |
| `bookings` | `Booking` and `Review` models, the booking request view, trip lifecycle helpers (status labels, cancel rules) and notification emails |
| `mybookings` | The renter's My bookings page, cancelling and reviews |
| `agencyrequests` | The agency's Booking requests inbox: approve, decline and cancel trips |
| `agencyfleet` | The agency's My listings: add, edit, status, photos and delete |
| `savedcars` | The renter's Saved cars page |
| `userprofile` | `Profile` (bio and photo) and `DriverLicense` models, the profile pages and the license form |
| `usersettings` | `UserSettings` model, the settings page and password change |

Other folders:
- `config/`: project settings (`settings.py`, plus `settings_test.py` for tests) and the root URL configuration.
- `templates/base.html`: the shared page layout and navigation.
- `static/css/site.css`: global styles and the design tokens (colours, borders, shadows) the feature stylesheets use.

## Setup (Windows / PowerShell)

1. Clone the repository and open a terminal in it.

2. Create and activate a virtual environment, then install the dependencies:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Create your `.env` file:
   ```powershell
   Copy-Item .env.example .env
   ```
   Fill in the `SUPABASE_DB_*` values from your Supabase project (Project Settings > Database). Then generate a secret key and paste it into `DJANGO_SECRET_KEY`:
   ```powershell
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```
   The site won't start without `DJANGO_SECRET_KEY`. `DJANGO_DEBUG` defaults to `True` and `DJANGO_ALLOWED_HOSTS` to `127.0.0.1,localhost`.

4. Create the database tables:
   ```powershell
   python manage.py migrate
   ```
   The first `fleet` migration enables the `pg_trgm` and `btree_gist` PostgreSQL extensions (`CREATE EXTENSION IF NOT EXISTS`), so there is no manual step as long as the database user may create extensions, as Supabase's default `postgres` user can.

5. Load the demo data and start the server:
   ```powershell
   python manage.py seed_fleet
   python manage.py runserver
   ```
   Open http://127.0.0.1:8000/.

## Demo accounts

`seed_fleet` creates these accounts, all with the password `password123`:

| Role | Email | Name |
|---|---|---|
| Agency | demo-agency@example.com | Demo Rentals |
| Renter | demo-renter@example.com | Maria |
| Renter | demo-renter2@example.com | Paolo |
| Renter | demo-renter3@example.com | Ana |

It also adds 14 cars in Cebu City, Mandaue, Lapu-Lapu, Talisay and Davao City, with past completed trips and reviews. One approved demo booking on the Toyota Vios starts 7 days from today: search those dates and the Vios is hidden.

`seed_fleet` is safe to re-run. It doesn't create duplicates, it resets the demo passwords to `password123`, and it moves the demo booking so it again starts 7 days from today.

## Running tests

```powershell
python manage.py test apps --settings=config.settings_test --keepdb
```

The test database (`autolease_test`) is created on the same Supabase server, so a full run takes several minutes. `--keepdb` reuses it between runs. To run a single app:

```powershell
python manage.py test apps.bookings --settings=config.settings_test --keepdb
```

## Emails in development

Email uses Django's console backend, so booking emails are printed in the terminal running `runserver`. Nothing is actually sent.

## Uploaded files

Car photos, profile photos and driver's license images are saved in the `media/` folder. It is git-ignored, and Django serves it only while `DEBUG` is on. The database stores only the file paths.

## Credits

Car photos are from Unsplash and Pexels, used under their free licences.
