from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.models import AgencyProfile

from .forms import AgencyEditForm, DriverLicenseForm, ProfileEditForm
from .models import DriverLicense


@login_required
def profile(request):
    """Read-only profile view."""
    user = request.user
    context = {
        'profile_user': user,
        'driver_license': DriverLicense.objects.filter(user=user).first(),
    }

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


@login_required
def license_edit(request):
    """Add or replace the user's driver's license (POST -> redirect -> GET)."""
    license_obj = DriverLicense.objects.filter(user=request.user).first()
    next_url = request.POST.get('next') or request.GET.get('next', '')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = ''

    if request.method == 'POST':
        form = DriverLicenseForm(request.POST, request.FILES, instance=license_obj)
        if form.is_valid():
            driver_license = form.save(commit=False)
            driver_license.user = request.user
            driver_license.save()
            messages.success(request, "Driver's license saved.")
            return redirect(next_url or 'userprofile:profile')
    else:
        form = DriverLicenseForm(instance=license_obj)

    context = {
        'form': form,
        'has_license': license_obj is not None,
        'next': next_url,
    }
    return render(request, 'userprofile/license_form.html', context)
