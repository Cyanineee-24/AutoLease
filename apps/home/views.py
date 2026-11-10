from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.fleet.forms import VehicleSearchForm
from apps.fleet.models import Vehicle


def landing(request):
    if request.user.is_authenticated:
        return redirect('home:dashboard')
    return render(request, 'home/landing.html')


@login_required
def dashboard(request):
    form = VehicleSearchForm(request.GET)
    form.is_valid()

    queryset = (
        Vehicle.objects.available()
        .for_listing(request.user)
        .search(**form.search_kwargs())
    )

    paginator = Paginator(queryset, 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'total_count': paginator.count,
        'search_qs': form.querystring(),
        'has_any_vehicles': Vehicle.objects.available().exists(),
        'date_error': form.has_error('end_date', code='end_before_start'),
        'q': request.GET.get('q', ''),
        'location': request.GET.get('location', ''),
        'start_date': request.GET.get('start_date', ''),
        'end_date': request.GET.get('end_date', ''),
        'today': timezone.localdate(),
    }
    return render(request, 'home/dashboard.html', context)
