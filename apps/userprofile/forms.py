from django import forms

from apps.accounts.models import AgencyProfile, CustomUser

from .models import Profile


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
