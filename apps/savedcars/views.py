from django.contrib.auth.decorators import login_required
from django.db.models import Max, Q
from django.shortcuts import render

from apps.fleet.models import Vehicle


@login_required
def saved_list(request):
    # The favorited_by filter matches one row per car (unique user+vehicle),
    # so the rating aggregates from for_listing are not multiplied.
    vehicles = list(
        Vehicle.objects.for_listing(request.user)
        .filter(favorited_by__user=request.user)
        .annotate(saved_at=Max('favorited_by__created_at', filter=Q(favorited_by__user=request.user)))
        .order_by('-saved_at', '-pk')
    )
    context = {
        'saved_count': len(vehicles),
        'available': [v for v in vehicles if v.status == 'available'],
        'unavailable': [v for v in vehicles if v.status != 'available'],
    }
    return render(request, 'savedcars/saved.html', context)
