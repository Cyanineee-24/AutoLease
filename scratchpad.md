# AutoLease — Manual QA Verification Scratchpad

This scratchpad provides an interactive checklist with exact steps, credentials, URLs, and expected behaviors to verify the Vehicle Browse (Home Dashboard) and Vehicle Detail features.

---

## 🛠️ How to View the Code Changes

You can inspect the changes using either your IDE's visual diff tools or the terminal:

### Option A: In the IDE (Recommended)
1. Open the **Source Control** panel on the left sidebar (`Ctrl + Shift + G`).
2. Click any file under **Changes** to see a side-by-side diff comparing the original with the new code.
3. Click any file under **Untracked** to view newly created files.

### Option B: In the Terminal
Run these commands in PowerShell from the project root:

```powershell
# 1. See all modified and new files
git status

# 2. View line-by-line diff of all modified files
git diff

# 3. View diff for a specific file
git diff apps/fleet/models.py
git diff apps/home/templates/home/dashboard.html
git diff static/css/fleet/fleet.css

# 4. View newly created untracked files
Get-ChildItem apps/fleet/forms.py, apps/fleet/urls.py, apps/fleet/views.py
```

---

## 🚀 Setup & Prerequisites

Before clicking through the features in your browser:

1. **Seed the database** (creates 14 vehicles, demo agency, renters, reviews, and bookings):
   ```powershell
   python manage.py seed_fleet
   ```
2. **Start the local development server**:
   ```powershell
   python manage.py runserver
   ```
3. **Open the browser**:
   Navigate to [http://127.0.0.1:8000/login/](http://127.0.0.1:8000/login/)

### Demo Credentials
| Role | Email | Password |
| :--- | :--- | :--- |
| **Demo Renter 1** | `demo-renter@example.com` | `password123` |
| **Demo Renter 2** | `demo-renter2@example.com` | `password123` |
| **Demo Renter 3** | `demo-renter3@example.com` | `password123` |
| **Demo Agency** | `demo-agency@example.com` | `password123` |

---

## 📋 Manual Verification Checklist

Check off each item as you verify it:

### Step 1: Authentication & Access Protection
- [ ] Open an Incognito/Private window.
- [ ] Go directly to [http://127.0.0.1:8000/dashboard/](http://127.0.0.1:8000/dashboard/).
  - **Action**: Check redirect.
  - **Expected**: Redirects to `/login/?next=/dashboard/`.
- [ ] Go directly to [http://127.0.0.1:8000/vehicles/1/](http://127.0.0.1:8000/vehicles/1/).
  - **Action**: Check redirect.
  - **Expected**: Redirects to `/login/?next=/vehicles/1/`.
- [ ] Log in with `demo-renter@example.com` / `password123`.
  - **Expected**: Successfully logged in and redirected to `/dashboard/`.

---

### Step 2: Dashboard Grid & Layout (Page 1)
- [ ] Look at the header row above the grid.
  - **Expected**: Displays **"Cars for rent"** on the left and **"14 cars available"** on the right.
- [ ] Count the listing cards on the first page.
  - **Expected**: Exactly **12 cards** rendered in the grid.
- [ ] Check card price formatting on card rows.
  - **Expected**: Prices show `₱2,500 per day` (grouped thousands, no unnecessary `.00` cents).
- [ ] Check rating chips on top-left of image area:
  - **Expected**: 3 vehicles show white **"Top rated"** pill badges (e.g. Vios, City, Xpander).
  - **Expected**: Cars with no reviews show **"New"** in place of the star rating.
- [ ] Verify image placeholders:
  - **Expected**: Since real photos are not uploaded yet, cards show flat tinted background tiles (`tone-0` through `tone-4`) with centered car SVGs.
- [ ] Check plate number privacy:
  - **Expected**: Plate numbers (e.g. `CAE 1001`) are **NEVER** displayed anywhere on the cards.

---

### Step 3: Pagination
- [ ] Scroll to the bottom of `/dashboard/`.
  - **Expected**: Pagination bar appears showing **"Previous"** (disabled/muted), **"Page 1 of 2"**, and active **"Next"** link.
- [ ] Click **"Next"**.
  - **Expected**: URL becomes `/dashboard/?page=2`.
  - **Expected**: Exactly **2 vehicles** are listed.
  - **Expected**: Pagination shows active **"Previous"** and disabled **"Next"**.
- [ ] Click **"Previous"** to return to Page 1.

---

### Step 4: Real-time Favorite (Heart) Toggle
- [ ] Locate the heart icon on the top-right of any vehicle card.
  - **Action**: Click the heart button.
  - **Expected**: The heart immediately fills with solid rose (`#E61E4D`) with a white outline.
  - **Expected**: **No page reload** occurs (inspect Network tab: sent asynchronous `POST` to `/vehicles/<pk>/favorite/` and received `{"favorited": true}`).
- [ ] Click the heart again.
  - **Expected**: Reverts back to translucent dark fill (`{"favorited": false}`).
- [ ] Favorite a card, then refresh the page (`F5`).
  - **Expected**: The card retains its saved state (`aria-pressed="true"` and rose fill).

---

### Step 5: Search & Typo Tolerance
- [ ] In the search pill, type `toyta` in the **"What"** field (intentional typo for Toyota) and click the search button.
  - **Expected**: Trigram similarity matches all **Toyota** cars (Vios, Innova, Fortuner, Hilux).
  - **Expected**: Input maintains `toyta`.
- [ ] In the search pill, type `vios` in **"What"** and submit.
  - **Expected**: Returns the Toyota Vios.
- [ ] Type `Cebu City` in **"Where"** and submit.
  - **Expected**: Header updates to **"Cars in Cebu City"**. Only cars in Cebu City appear.
- [ ] Test location typo: type `cebu cty` in **"Where"** and submit.
  - **Expected**: Trigram similarity still finds the Cebu City vehicles.

---

### Step 6: Booking Date Exclusion Demo
- [ ] When `seed_fleet` ran, it created an approved future booking for the **Toyota Vios (`CAE 1001`)** from **2026-11-10 to 2026-11-15**.
- [ ] In the search pill, set:
  - **Pick-up**: `2026-11-10`
  - **Drop-off**: `2026-11-15`
  - Click Search.
  - **Expected**: The Toyota Vios is **hidden** from the results because of the approved booking overlap.
- [ ] Change dates to **Pick-up: `2026-11-16`** and **Drop-off: `2026-11-20`** (after the booking).
  - Click Search.
  - **Expected**: The Toyota Vios reappears!
- [ ] Test inclusive boundary: set **Pick-up: `2026-11-15`** (the exact day the booking ends).
  - **Expected**: The Toyota Vios is **hidden** (inclusive day boundary check).

---

### Step 7: Date Validation Error State
- [ ] In the search pill, select:
  - **Pick-up**: `2026-11-20`
  - **Drop-off**: `2026-11-15` (Drop-off is BEFORE Pick-up)
  - Click Search.
  - **Expected**: A rose alert displays directly below the search bar:
    `Drop-off must be on or after pick-up.`
  - **Expected**: Vehicles are still displayed below (invalid dates are safely ignored).

---

### Step 8: Empty Search State & Clear Search
- [ ] In **"What"**, type `Ferrari` (make not in database) and click Search.
  - **Expected**: Displays empty state with icon and heading: **"No cars match your search"**.
  - **Expected**: Subtitle: `Try a different make, city, or dates.`
  - **Expected**: A **"Clear search"** button is displayed.
- [ ] Click **"Clear search"**.
  - **Expected**: Redirects to `/dashboard/` with search cleared and all 14 vehicles shown.

---

### Step 9: Vehicle Detail Page
- [ ] Click anywhere on a vehicle card (e.g. 2022 Toyota Vios).
  - **Expected**: Navigates to `/vehicles/<pk>/`.
  - **Expected**: Whole card is clickable via stretched link.
- [ ] Check the **"Back to results"** link at the top.
  - **Expected**: Shows arrow icon and text "Back to results". If you came from a search (e.g. `?q=vios`), clicking it preserves your search filter.
- [ ] Check Title and Save button:
  - **Expected**: `<h1>2022 Toyota Vios</h1>`.
  - **Expected**: Top-right shows "Save" heart button with text label. Clicking it toggles between "Save" and "Saved" asynchronously.
  - **Expected**: **NO** share button present.
- [ ] Check Host Section:
  - **Expected**: Shows rose avatar circle with initials (e.g. `"DR"` for Demo Rentals).
  - **Expected**: Displays **"Hosted by Demo Rentals"**.
  - **Expected**: Displays **"Contact: 0917 123 4567"** (because `show_contact_number=True`).
- [ ] Check "What this car offers" Specs:
  - **Expected**: Rows for Transmission, Fuel type, Seats, Color, Year with hairline borders.
  - **Expected**: Plate number is **NOT** present anywhere on the page.
- [ ] Check Reviews Section:
  - **Expected**: Reviewers show first name only (e.g., `"Maria"`, `"Paolo"`, `"Ana"`).
  - **Expected**: Date format is `Month Year` (e.g., `January 2024`).
  - **Expected**: **NO** email address or username is visible anywhere.

---

### Step 10: Live Booking Card & Calculations
- [ ] Inspect the sticky card on the right side of the detail page:
  - **Expected**: Shows rate (e.g., `₱2,500 per day`).
  - **Expected**: Button reads **"Booking opens soon"** and is disabled (`cursor: not-allowed`).
  - **Expected**: Helper text: `You won't be charged. The agency reviews your request first.`
  - **Expected**: Before dates are picked, shows `Select your dates to see the total`.
- [ ] Select Pick-up and Drop-off dates:
  - **Pick-up**: Oct 14
  - **Drop-off**: Oct 17
  - **Action**: Watch breakdown update live without reload.
  - **Expected**: Displays `₱2,500 x 4 days` (inclusive count: Oct 14, 15, 16, 17 = 4 days).
  - **Expected**: Subtotal and Estimated Total show `₱10,000` formatted with PHP currency formatting.
- [ ] Test reverse dates in booking card:
  - Set Drop-off earlier than Pick-up.
  - **Expected**: Shows inline error `Drop-off must be on or after pick-up.` and hides breakdown.
- [ ] Bottom notice:
  - **Expected**: Shows `A driver's license is required to request this car`.

---

## 🧪 Automated Test Verification

You can re-run the full automated test suite at any time:

```powershell
python manage.py test --settings=config.test_settings --keepdb
```
**Expected result**: `Ran 42 tests ... OK`
