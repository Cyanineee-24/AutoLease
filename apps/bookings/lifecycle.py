"""Date-based trip lifecycle for bookings.

Pure functions (no request access). An 'approved' booking stays 'approved' in
the database until the renter reviews it, so screens derive what to show
from the dates at display time.
"""

AGENCY_CANCEL_PREFIX = 'Cancelled by the agency: '


def trip_phase(booking, today):
    """'upcoming', 'in_progress' or 'finished' for approved bookings; None otherwise."""
    if booking.status != 'approved':
        return None
    if today < booking.start_date:
        return 'upcoming'
    if today <= booking.end_date:
        return 'in_progress'
    return 'finished'


def _cancelled_by_agency(booking):
    return booking.status == 'cancelled' and (booking.agency_response or '').startswith(AGENCY_CANCEL_PREFIX)


def display_status(booking, today):
    """(key, label) for a status badge; the key matches a .status-badge--<key> CSS rule."""
    if booking.status == 'pending':
        return 'pending', 'Pending'
    if booking.status == 'approved':
        phase = trip_phase(booking, today)
        if phase == 'upcoming':
            return 'upcoming', 'Upcoming'
        if phase == 'in_progress':
            return 'in_progress', 'In progress'
        return 'completed', 'Completed'
    if booking.status == 'completed':
        return 'completed', 'Completed'
    if booking.status == 'declined':
        return 'declined', 'Declined'
    if booking.status == 'cancelled':
        if _cancelled_by_agency(booking):
            return 'cancelled', 'Cancelled by agency'
        return 'cancelled', 'Cancelled'
    return booking.status, booking.get_status_display()


def can_cancel(booking, today):
    """Pending requests, or approved trips that haven't started yet."""
    if booking.status == 'pending':
        return True
    return booking.status == 'approved' and today < booking.start_date


def agency_cancel_reason(booking):
    """The agency's reason if it cancelled this booking, else ''."""
    if not _cancelled_by_agency(booking):
        return ''
    return booking.agency_response[len(AGENCY_CANCEL_PREFIX):]
