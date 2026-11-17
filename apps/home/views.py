from django.contrib.postgres.search import TrigramSimilarity, TrigramWordSimilarity
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Max, Q, Value, When
from django.db.models.functions import Greatest
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.fleet.forms import VehicleSearchForm
from apps.fleet.models import Vehicle

MAX_SUGGESTIONS = 6
# Same threshold as VehicleQuerySet.search for whole-value similarity.
SIMILARITY_THRESHOLD = 0.3
# Word similarity compares the term with the closest word in the value, so a
# typo in one word of a longer value ("cebo" for "Cebu City") still matches.
WORD_SIMILARITY_THRESHOLD = 0.5


def landing(request):
    if request.user.is_authenticated:
        return redirect('home:dashboard')
    return render(request, 'home/landing.html')


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


def _fuzzy(field, term):
    """Best of whole-value and word trigram similarity, for ordering."""
    return Greatest(TrigramSimilarity(field, term), TrigramWordSimilarity(term, field))


def _matches(field, term):
    """Q for one field: contains the term, or is close to it (a typo)."""
    return (
        Q(**{f'{field}__icontains': term})
        | Q(**{f'{field}_sim__gt': SIMILARITY_THRESHOLD})
        | Q(**{f'{field}_word__gt': WORD_SIMILARITY_THRESHOLD})
    )


def _with_similarity(queryset, term, *fields):
    """alias() rather than annotate(): aliases stay out of GROUP BY."""
    aliases = {}
    for field in fields:
        aliases[f'{field}_sim'] = TrigramSimilarity(field, term)
        aliases[f'{field}_word'] = TrigramWordSimilarity(term, field)
    return queryset.alias(**aliases)


def _starts_with(term, *fields):
    """1 when any of the fields starts with the term, else 0 (best matches first)."""
    condition = Q()
    for field in fields:
        condition |= Q(**{f'{field}__istartswith': term})
    return Max(Case(When(condition, then=Value(1)), default=Value(0), output_field=IntegerField()))


def _item(value, count):
    return {'value': value, 'label': value, 'meta': f'{count} car{"s" if count != 1 else ""}'}


def _city_suggestions(term):
    rows = (
        _with_similarity(Vehicle.objects.available(), term, 'city')
        .filter(_matches('city', term))
        .values('city')
        .annotate(cars=Count('pk'), starts=_starts_with(term, 'city'), score=Max(_fuzzy('city', term)))
        .order_by('-starts', '-score', 'city')[:MAX_SUGGESTIONS]
    )
    return [_item(row['city'], row['cars']) for row in rows]


def _vehicle_suggestions(term):
    """Makes first (when the make itself matches), then make + model pairs."""
    available = Vehicle.objects.available()
    makes = (
        _with_similarity(available, term, 'make')
        .filter(_matches('make', term))
        .values('make')
        .annotate(cars=Count('pk'), starts=_starts_with(term, 'make'), score=Max(_fuzzy('make', term)))
        .order_by('-starts', '-score', 'make')[:MAX_SUGGESTIONS]
    )
    items = [_item(row['make'], row['cars']) for row in makes]
    if len(items) >= MAX_SUGGESTIONS:
        return items

    models = (
        _with_similarity(available, term, 'make', 'model')
        .filter(_matches('make', term) | _matches('model', term))
        .values('make', 'model')
        .annotate(
            cars=Count('pk'),
            starts=_starts_with(term, 'make', 'model'),
            score=Max(Greatest(_fuzzy('make', term), _fuzzy('model', term))),
        )
        .order_by('-starts', '-score', 'make', 'model')[:MAX_SUGGESTIONS - len(items)]
    )
    items += [_item(f'{row["make"]} {row["model"]}', row['cars']) for row in models]
    return items


@require_GET
def suggest(request):
    """Search-bar suggestions from available cars: cities for Where, makes and models for What."""
    field = request.GET.get('field', '')
    term = request.GET.get('term', '').strip()[:100]
    if not term or field not in ('location', 'q'):
        suggestions = []
    elif field == 'location':
        suggestions = _city_suggestions(term)
    else:
        suggestions = _vehicle_suggestions(term)
    response = JsonResponse({'suggestions': suggestions})
    response['Cache-Control'] = 'no-store'
    return response
