from django.contrib.auth.decorators import login_required
from django.db.models import OuterRef, Subquery
from django.shortcuts import render

from apps.fleet.models import Favorite, Vehicle


@login_required
def saved_list(request):
    # Inner query: the ids of the cars this user has saved.
    saved_ids = Favorite.objects.filter(user=request.user).values('vehicle_id')
    # When each car was saved (unique user+vehicle, so at most one row).
    saved_at = Favorite.objects.filter(user=request.user, vehicle=OuterRef('pk')).values('created_at')[:1]
    # Outer query: the listing cars whose id is in the inner result, newest saved first.
    vehicles = list(
        Vehicle.objects.for_listing(request.user)
        .filter(id__in=Subquery(saved_ids))
        .annotate(saved_at=Subquery(saved_at))
        .order_by('-saved_at', '-pk')
    )
    context = {
        'saved_count': len(vehicles),
        'available': [v for v in vehicles if v.status == 'available'],
        'unavailable': [v for v in vehicles if v.status != 'available'],
    }
    return render(request, 'savedcars/saved.html', context)
