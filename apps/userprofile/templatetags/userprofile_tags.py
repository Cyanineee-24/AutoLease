from django import template
from django.core.exceptions import ObjectDoesNotExist

register = template.Library()


@register.filter
def avatar_url(user):
    """URL of the user's profile photo, or '' (guest, no Profile row, or no photo).

    Never raises, so base.html can call it on every page.
    """
    if not getattr(user, 'is_authenticated', False):
        return ''
    try:
        image = user.profile.profile_image
    except ObjectDoesNotExist:
        return ''
    if not image:
        return ''
    try:
        return image.url
    except ValueError:
        return ''
