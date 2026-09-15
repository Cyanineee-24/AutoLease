from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ProfileForm
from .models import Profile


@login_required
def profile(request):
    user = request.user
    profile_obj, _created = Profile.objects.get_or_create(user=user)

    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile_obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('userprofile:profile')
    else:
        form = ProfileForm(instance=profile_obj)

    context = {
        'profile_user': user,
        'form': form,
    }

    if user.is_agency:
        try:
            context['agency_profile'] = user.agency_profile
        except user.agency_profile.RelatedObjectDoesNotExist:
            pass

    return render(request, 'userprofile/profile.html', context)
