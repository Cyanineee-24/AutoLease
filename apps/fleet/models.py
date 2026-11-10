from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    SearchVector,
    SearchVectorField,
    TrigramSimilarity,
)
from django.db import models
from django.db.models import Avg, Count, F, Q
from django.db.models.functions import Greatest


class VehicleQuerySet(models.QuerySet):
    """Custom queryset for vehicle browsing, search, and annotation."""

    def available(self):
        return self.filter(status='available')

    def with_ratings(self):
        return self.annotate(
            avg_rating=Avg('bookings__review__rating'),
            review_count=Count('bookings__review', distinct=True),
        )

    def for_listing(self, user):
        from .models import Favorite  # local import for clarity within manager

        qs = self.select_related('agency').prefetch_related('images').with_ratings()
        if user.is_authenticated:
            qs = qs.annotate(
                is_favorited=models.Exists(
                    Favorite.objects.filter(
                        user=user,
                        vehicle=models.OuterRef('pk'),
                    )
                )
            )
        else:
            qs = qs.annotate(
                is_favorited=models.Value(False, output_field=models.BooleanField())
            )
        return qs

    def search(self, q=None, location=None, start=None, end=None):
        qs = self

        if q:
            query = SearchQuery(q, config='english', search_type='websearch')
            similarity = Greatest(
                TrigramSimilarity('make', q),
                TrigramSimilarity('model', q),
            )
            qs = qs.annotate(similarity=similarity)
            qs = qs.filter(
                Q(search_vector=query)
                | Q(make__icontains=q)
                | Q(model__icontains=q)
                | Q(similarity__gt=0.3)
            )
            relevance = Greatest(
                SearchRank(F('search_vector'), query),
                F('similarity'),
            )
            qs = qs.annotate(relevance=relevance).order_by(
                '-relevance', '-created_at', '-pk'
            )
        else:
            qs = qs.order_by('-created_at', '-pk')

        if location:
            city_similarity = TrigramSimilarity('city', location)
            qs = qs.annotate(city_similarity=city_similarity).filter(
                Q(city__icontains=location) | Q(city_similarity__gt=0.3)
            )

        if start and end and end >= start:
            Booking = __import__('django.apps', fromlist=['apps']).apps.get_model(
                'bookings', 'Booking'
            )
            overlapping = Booking.objects.filter(
                vehicle=models.OuterRef('pk'),
                status='approved',
                start_date__lte=end,
                end_date__gte=start,
            )
            qs = qs.filter(~models.Exists(overlapping))

        return qs


class Vehicle(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('unavailable', 'Unavailable'),
        ('maintenance', 'Maintenance'),
    ]

    agency = models.ForeignKey(
        'accounts.AgencyProfile',
        on_delete=models.CASCADE,
        related_name='vehicles',
    )
    make = models.CharField(max_length=80)
    model = models.CharField(max_length=80)
    year = models.SmallIntegerField()
    plate_number = models.CharField(max_length=20, unique=True)
    transmission = models.CharField(max_length=20)
    fuel_type = models.CharField(max_length=20)
    seats = models.SmallIntegerField()
    color = models.CharField(max_length=40)
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2)
    city = models.CharField(max_length=120)
    status = models.CharField(
        max_length=20,
        default='available',
        choices=STATUS_CHOICES,
    )
    search_vector = models.GeneratedField(
        expression=SearchVector('make', 'model', 'city', config='english'),
        output_field=SearchVectorField(),
        db_persist=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = VehicleQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=['available', 'unavailable', 'maintenance']
                ),
                name='vehicle_status_valid',
            ),
        ]
        indexes = [
            GinIndex(
                fields=['city'],
                name='vehicle_city_trgm',
                opclasses=['gin_trgm_ops'],
            ),
            GinIndex(
                fields=['make'],
                name='vehicle_make_trgm',
                opclasses=['gin_trgm_ops'],
            ),
            GinIndex(
                fields=['model'],
                name='vehicle_model_trgm',
                opclasses=['gin_trgm_ops'],
            ),
            GinIndex(
                fields=['search_vector'],
                name='vehicle_search_vector_gin',
            ),
        ]

    def __str__(self):
        return f'{self.year} {self.make} {self.model} ({self.plate_number})'

    # ------------------------------------------------------------------
    # Properties (work from prefetched data, no extra queries)
    # ------------------------------------------------------------------

    @property
    def gallery_images(self):
        """Primary first, then by sort_order, id."""
        imgs = list(self.images.all())
        imgs.sort(key=lambda i: (not i.is_primary, i.sort_order, i.id))
        return imgs

    @property
    def primary_image(self):
        imgs = self.gallery_images
        return imgs[0] if imgs else None

    @property
    def is_top_rated(self):
        avg = getattr(self, 'avg_rating', None) or 0
        count = getattr(self, 'review_count', None) or 0
        return avg >= 4.8 and count >= 3

    @property
    def placeholder_tone(self):
        return self.pk % 5


class VehicleImage(models.Model):
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='fleet/vehicles/')
    is_primary = models.BooleanField(default=False)
    sort_order = models.SmallIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Image for {self.vehicle} (order={self.sort_order})'


class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorites',
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='favorited_by',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'vehicle'],
                name='unique_favorite_user_vehicle',
            ),
        ]

    def __str__(self):
        return f'{self.user} → {self.vehicle}'
