from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import UserSettingsForm
from .models import UserSettings


@login_required
def settings_view(request):
    user_settings, _created = UserSettings.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = UserSettingsForm(request.POST, instance=user_settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Settings saved.')
            return redirect('usersettings:settings')
    else:
        form = UserSettingsForm(instance=user_settings)

    return render(request, 'usersettings/settings.html', {'form': form})
