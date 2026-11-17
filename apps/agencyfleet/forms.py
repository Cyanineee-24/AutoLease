import re
from decimal import Decimal

from django import forms
from django.core.validators import FileExtensionValidator
from django.utils import timezone

from apps.fleet.models import Vehicle

# These choices live only in the form. The model keeps plain CharFields, so
# adding choices here never creates a migration.
TRANSMISSION_CHOICES = [
    ('Automatic', 'Automatic'),
    ('Manual', 'Manual'),
]
FUEL_TYPE_CHOICES = [
    ('Gasoline', 'Gasoline'),
    ('Diesel', 'Diesel'),
    ('Hybrid', 'Hybrid'),
    ('Electric', 'Electric'),
]

MIN_YEAR = 1990
MIN_SEATS = 2
MAX_SEATS = 15
MAX_DAILY_RATE = Decimal('100000')


class VehicleForm(forms.ModelForm):
    transmission = forms.ChoiceField(choices=TRANSMISSION_CHOICES)
    fuel_type = forms.ChoiceField(choices=FUEL_TYPE_CHOICES, label='Fuel type')

    class Meta:
        model = Vehicle
        fields = [
            'make', 'model', 'year', 'plate_number', 'transmission',
            'fuel_type', 'seats', 'color', 'daily_rate', 'city',
        ]
        labels = {
            'plate_number': 'Plate number',
            'daily_rate': 'Daily rate (₱)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep a legacy value (e.g. "CVT") selectable so editing doesn't wipe it.
        for name, choices in (('transmission', TRANSMISSION_CHOICES), ('fuel_type', FUEL_TYPE_CHOICES)):
            current = getattr(self.instance, name, '') if self.instance.pk else ''
            if current and current not in {value for value, _ in choices}:
                self.fields[name].choices = [*choices, (current, current)]

        max_year = timezone.localdate().year + 1
        self.fields['year'].widget.attrs.update({'min': MIN_YEAR, 'max': max_year})
        self.fields['seats'].widget.attrs.update({'min': MIN_SEATS, 'max': MAX_SEATS})
        self.fields['daily_rate'].widget.attrs.update({'min': '1', 'max': '100000', 'step': '0.01'})
        self.fields['plate_number'].widget.attrs.update({'autocapitalize': 'characters'})

    # make, model, color and city are required, and Django's CharField strips
    # surrounding whitespace by default, so they need no extra cleaning.

    def clean_year(self):
        year = self.cleaned_data['year']
        max_year = timezone.localdate().year + 1
        if year < MIN_YEAR or year > max_year:
            raise forms.ValidationError(f'Enter a year between {MIN_YEAR} and {max_year}.')
        return year

    def clean_seats(self):
        seats = self.cleaned_data['seats']
        if seats < MIN_SEATS or seats > MAX_SEATS:
            raise forms.ValidationError(f'Seats must be between {MIN_SEATS} and {MAX_SEATS}.')
        return seats

    def clean_daily_rate(self):
        rate = self.cleaned_data['daily_rate']
        if rate <= 0:
            raise forms.ValidationError('Enter a daily rate above ₱0.')
        if rate > MAX_DAILY_RATE:
            raise forms.ValidationError("The daily rate can't be more than ₱100,000.")
        return rate

    def clean_plate_number(self):
        plate = re.sub(r'\s+', ' ', self.cleaned_data['plate_number']).strip().upper()
        if not plate:
            raise forms.ValidationError('Enter a plate number.')
        duplicates = Vehicle.objects.filter(plate_number__iexact=plate)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError('Another car already uses this plate number.')
        return plate


MAX_PHOTOS_PER_CAR = 10
MAX_PHOTO_BYTES = 5 * 1024 * 1024
PHOTO_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']


class MultipleFileInput(forms.FileInput):
    """A file input that accepts several files (Django's documented pattern)."""

    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    """Cleans one upload or a list of them and always returns a list.

    Every file gets the full ImageField checks (Pillow confirms it's a real
    image), the extension validator and the size limit. An error names the
    file it belongs to, e.g. "beach.gif: Use a JPG, PNG or WebP image."
    """

    widget = MultipleFileInput

    def clean(self, data, initial=None):
        uploads = data if isinstance(data, (list, tuple)) else [data]
        uploads = [upload for upload in uploads if upload]
        if not uploads:
            raise forms.ValidationError(self.error_messages['required'], code='required')

        check_one = super().clean
        cleaned = []
        for upload in uploads:
            try:
                image = check_one(upload, initial)
                if image.size > MAX_PHOTO_BYTES:
                    raise forms.ValidationError('Photos must be 5 MB or smaller.')
            except forms.ValidationError as error:
                raise forms.ValidationError(f'{upload.name}: {error.messages[0]}') from error
            cleaned.append(image)
        return cleaned


class VehiclePhotoForm(forms.Form):
    """One or more photos per submit; cleaned_data['image'] is a list, in the order chosen."""

    image = MultipleImageField(
        label='Add photos',
        validators=[FileExtensionValidator(PHOTO_EXTENSIONS, message='Use a JPG, PNG or WebP image.')],
        error_messages={
            'required': 'Choose a photo to upload.',
            'invalid_image': "That file isn't an image we can read. Use a JPG, PNG or WebP photo.",
        },
    )
