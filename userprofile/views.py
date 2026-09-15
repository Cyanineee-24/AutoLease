from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def profile(request):
    user = request.user
    context = {'profile_user': user}

    if user.is_agency:
        try:
            context['agency_profile'] = user.agency_profile
        except user.agency_profile.RelatedObjectDoesNotExist:
            pass

    return render(request, 'userprofile/profile.html', context)
