"""Booking notification emails.

Each public function emails one user about one booking event. Emails respect
the recipient's "Email notifications" setting, are sent only after the
surrounding transaction commits, and never raise: a mail failure is logged
and the booking action carries on.
"""
import logging

from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

from apps.usersettings.models import UserSettings

from .lifecycle import agency_cancel_reason

logger = logging.getLogger(__name__)


def _wants_email(user):
    """False for users without an email or who turned email notifications off."""
    if user is None or not user.email:
        return False
    enabled = (
        UserSettings.objects.filter(user=user)
        .values_list('email_notifications', flat=True)
        .first()
    )
    return enabled is None or bool(enabled)  # no settings row → default on


def _send(user, subject, template_name, context):
    if not _wants_email(user):
        return
    recipient = user.email

    def deliver():
        try:
            body = render_to_string(f'bookings/email/{template_name}.txt', context)
            send_mail(subject, body, None, [recipient])  # None → DEFAULT_FROM_EMAIL
        except Exception:
            logger.exception('Could not send the %s email to user %s.', template_name, user.pk)

    transaction.on_commit(deliver)


def _short_date(day):
    return f'{day:%b} {day.day}'


def _date_range(booking):
    return f'{_short_date(booking.start_date)}–{_short_date(booking.end_date)}'


def _context(booking, request, link_name):
    days = (booking.end_date - booking.start_date).days + 1
    renter_first = (booking.renter.first_name or '').strip()
    return {
        'booking': booking,
        'vehicle': booking.vehicle,
        'agency_name': booking.vehicle.agency.business_name,
        'renter_name': renter_first or 'there',
        'renter_label': renter_first or 'A renter',
        'days': days,
        'total': booking.daily_rate_snapshot * days,
        'link': request.build_absolute_uri(reverse(link_name)),
    }


def _car(booking):
    return f'{booking.vehicle.make} {booking.vehicle.model}'


def notify_new_request(booking, request):
    """To the agency: a renter asked for one of its cars."""
    _send(
        booking.vehicle.agency.user,
        f'New booking request: {_car(booking)}, {_date_range(booking)}',
        'new_request',
        _context(booking, request, 'agencyrequests:inbox'),
    )


def notify_decision(booking, request):
    """To the renter: their request was approved or declined."""
    if booking.status == 'approved':
        subject, template = f'Your trip is confirmed: {_car(booking)}', 'approved'
    elif booking.status == 'declined':
        subject, template = f"Your request wasn't accepted: {_car(booking)}", 'declined'
    else:
        return
    _send(booking.renter, subject, template, _context(booking, request, 'mybookings:list'))


def notify_cancelled_by_renter(booking, request):
    """To the agency: a renter cancelled an approved trip."""
    _send(
        booking.vehicle.agency.user,
        f'Trip cancelled by renter: {_car(booking)}, {_date_range(booking)}',
        'cancelled_by_renter',
        _context(booking, request, 'agencyrequests:inbox'),
    )


def notify_cancelled_by_agency(booking, request):
    """To the renter: the agency cancelled their trip, with its reason."""
    context = _context(booking, request, 'mybookings:list')
    context['reason'] = agency_cancel_reason(booking)
    _send(
        booking.renter,
        f'Your trip was cancelled by the agency: {_car(booking)}',
        'cancelled_by_agency',
        context,
    )
