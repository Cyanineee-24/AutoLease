from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .models import AgencyProfile


def agency_required(view):
    """Allow only users flagged as agency who have an AgencyProfile."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_agency or not AgencyProfile.objects.filter(user=request.user).exists():
            messages.error(request, 'Only rental agencies can manage booking requests.')
            return redirect('home:dashboard')
        return view(request, *args, **kwargs)

    return wrapper
