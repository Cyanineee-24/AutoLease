from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models


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
