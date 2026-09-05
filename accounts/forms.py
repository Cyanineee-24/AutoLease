from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction

from .models import AgencyProfile, CustomUser


class RegistrationForm(UserCreationForm):
    ACCOUNT_TYPE_RENTER = 'renter'
    ACCOUNT_TYPE_AGENCY = 'agency'
    ACCOUNT_TYPE_CHOICES = [
        (ACCOUNT_TYPE_RENTER, 'I want to rent a vehicle'),
        (ACCOUNT_TYPE_AGENCY, 'I manage a rental business'),
    ]

    email = forms.EmailField(label='Email address')
    account_type = forms.ChoiceField(
        choices=ACCOUNT_TYPE_CHOICES,
        widget=forms.RadioSelect,
        label='I am joining as',
    )
    business_name = forms.CharField(required=False, max_length=255)
    contact_number = forms.CharField(required=False, max_length=50)

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = (
            'email',
            'account_type',
            'business_name',
            'contact_number',
            'password1',
            'password2',
        )

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('account_type') == self.ACCOUNT_TYPE_AGENCY:
            if not cleaned_data.get('business_name'):
                self.add_error('business_name', 'Enter your business name.')
            if not cleaned_data.get('contact_number'):
                self.add_error('contact_number', 'Enter a contact number.')
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.username = user.email
        user.is_renter = self.cleaned_data['account_type'] == self.ACCOUNT_TYPE_RENTER
        user.is_agency = self.cleaned_data['account_type'] == self.ACCOUNT_TYPE_AGENCY

        if commit:
            user.save()
            if user.is_agency:
                AgencyProfile.objects.create(
                    user=user,
                    business_name=self.cleaned_data['business_name'],
                    contact_number=self.cleaned_data['contact_number'],
                )
        return user
