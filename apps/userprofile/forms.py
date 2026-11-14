from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import FileExtensionValidator

from apps.accounts.models import AgencyProfile, CustomUser

from django.utils import timezone

from .models import DriverLicense, Profile

MAX_BIO_LENGTH = 500
MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024
PROFILE_PHOTO_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']


class ProfileForm(forms.ModelForm):
    """Bio and profile photo. Both optional; the photo can be cleared."""

    bio = forms.CharField(
        required=False,
        max_length=MAX_BIO_LENGTH,
        widget=forms.Textarea(attrs={'rows': 4, 'maxlength': MAX_BIO_LENGTH}),
        error_messages={'max_length': 'Keep your bio to 500 characters or fewer.'},
    )
    profile_image = forms.ImageField(
        required=False,
        label='Profile photo',
        validators=[FileExtensionValidator(PROFILE_PHOTO_EXTENSIONS, message='Use a JPG, PNG or WebP image.')],
        widget=forms.ClearableFileInput(attrs={'accept': '.jpg,.jpeg,.png,.webp'}),
        error_messages={
            'invalid_image': "That file isn't an image we can read. Use a JPG, PNG or WebP photo.",
        },
    )

    class Meta:
        model = Profile
        fields = ['bio', 'profile_image']

    def clean_profile_image(self):
        image = self.cleaned_data.get('profile_image')
        # Only a new upload needs the size check; False means "clear", a FieldFile means "unchanged".
        if isinstance(image, UploadedFile) and image.size > MAX_PROFILE_PHOTO_BYTES:
            raise forms.ValidationError('Profile photos must be 2 MB or smaller.')
        return image


class ProfileEditForm(forms.ModelForm):
    """Editable user fields: first_name, last_name, contact_number.
    Email/username editing is out of scope (email == username in this project)."""

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'contact_number']


class AgencyEditForm(forms.ModelForm):
    """Agency-specific fields. Only rendered when request.user.is_agency."""

    class Meta:
        model = AgencyProfile
        fields = ['business_name', 'contact_number']


class DriverLicenseForm(forms.ModelForm):
    """Driver's license on file; required before requesting a booking."""

    class Meta:
        model = DriverLicense
        fields = ['license_number', 'issuing_country', 'expiry_date', 'license_image']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_expiry_date(self):
        expiry = self.cleaned_data['expiry_date']
        if expiry < timezone.localdate():
            raise forms.ValidationError('This license has expired.')
        return expiry
