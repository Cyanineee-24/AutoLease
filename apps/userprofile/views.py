from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.accounts.models import AgencyProfile

from .forms import AgencyEditForm, ProfileEditForm


@login_required
def profile(request):
    """Read-only profile view."""
    user = request.user
    context = {'profile_user': user}

    if user.is_agency:
        try:
            context['agency_profile'] = user.agency_profile
        except AgencyProfile.DoesNotExist:
            pass

    return render(request, 'userprofile/profile.html', context)


@login_required
def profile_edit(request):
    """Edit profile view — two forms in one page (user + optional agency)."""
    user = request.user
    agency_profile = None

    if user.is_agency:
        try:
            agency_profile = user.agency_profile
        except AgencyProfile.DoesNotExist:
            pass

    if request.method == 'POST':
        user_form = ProfileEditForm(request.POST, instance=user)
        agency_form = (
            AgencyEditForm(request.POST, instance=agency_profile, prefix='agency')
            if agency_profile
            else None
        )

        # Validate both forms (or just user form for non-agency)
        user_valid = user_form.is_valid()
        agency_valid = agency_form.is_valid() if agency_form else True

        if user_valid and agency_valid:
            user_form.save()
            if agency_form:
                agency_form.save()
            messages.success(request, 'Profile updated.')
            return redirect('userprofile:profile')
    else:
        user_form = ProfileEditForm(instance=user)
        agency_form = (
            AgencyEditForm(instance=agency_profile, prefix='agency')
            if agency_profile
            else None
        )

    context = {
        'user_form': user_form,
        'agency_form': agency_form,
    }
    return render(request, 'userprofile/profile_edit.html', context)
