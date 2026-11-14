from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.models import AgencyProfile

from .forms import AgencyEditForm, DriverLicenseForm, ProfileEditForm, ProfileForm
from .models import DriverLicense, Profile


@login_required
def profile(request):
    """Read-only profile view."""
    user = request.user
    context = {
        'profile_user': user,
        'profile': Profile.objects.filter(user=user).first(),
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
    """Edit profile view: user fields, bio/photo, and agency details for agencies."""
    user = request.user
    agency_profile = None

    if user.is_agency:
        try:
            agency_profile = user.agency_profile
        except AgencyProfile.DoesNotExist:
            pass

    # The signal creates this row; get_or_create covers any user it missed.
    profile_obj, _ = Profile.objects.get_or_create(user=user)
    # Captured before binding: an invalid POST mutates the form's instance.
    old_image_name = profile_obj.profile_image.name if profile_obj.profile_image else ''
    current_image_url = profile_obj.profile_image.url if old_image_name else ''

    if request.method == 'POST':
        user_form = ProfileEditForm(request.POST, instance=user)
        profile_form = ProfileForm(request.POST, request.FILES, instance=profile_obj, prefix='profile')
        agency_form = (
            AgencyEditForm(request.POST, instance=agency_profile, prefix='agency')
            if agency_profile
            else None
        )

        # Validate every form so all errors show at once; save only if all pass.
        user_valid = user_form.is_valid()
        profile_valid = profile_form.is_valid()
        agency_valid = agency_form.is_valid() if agency_form else True

        if user_valid and profile_valid and agency_valid:
            user_form.save()
            saved_profile = profile_form.save()
            if agency_form:
                agency_form.save()
            new_image_name = saved_profile.profile_image.name if saved_profile.profile_image else ''
            if old_image_name and old_image_name != new_image_name:
                # Replaced or cleared: remove the old file. Deleting by name keeps the
                # saved instance's new value intact (FieldFile.delete would reset it).
                saved_profile.profile_image.storage.delete(old_image_name)
            messages.success(request, 'Profile updated.')
            return redirect('userprofile:profile')
    else:
        user_form = ProfileEditForm(instance=user)
        profile_form = ProfileForm(instance=profile_obj, prefix='profile')
        agency_form = (
            AgencyEditForm(instance=agency_profile, prefix='agency')
            if agency_profile
            else None
        )

    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'agency_form': agency_form,
        'current_image_url': current_image_url,
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
