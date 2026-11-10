from django import forms

from apps.accounts.models import AgencyProfile, CustomUser

from django.utils import timezone

from .models import DriverLicense, Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['bio', 'profile_image']


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
