from urllib.parse import urlencode

from django import forms
from django.core.exceptions import ValidationError


class VehicleSearchForm(forms.Form):
    """Search form for vehicle browsing — always bound to request.GET."""

    q = forms.CharField(required=False, max_length=80, strip=True)
    location = forms.CharField(required=False, max_length=120, strip=True)
    start_date = forms.DateField(required=False)
    end_date = forms.DateField(required=False)

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            self.add_error(
                'end_date',
                ValidationError(
                    'Drop-off must be on or after pick-up.',
                    code='end_before_start',
                ),
            )
        return cleaned

    def search_kwargs(self):
        """Build kwargs dict for Vehicle.objects.search(...)."""
        data = self.cleaned_data
        kwargs = {}
        if data.get('q'):
            kwargs['q'] = data['q']
        if data.get('location'):
            kwargs['location'] = data['location']
        # Include dates only when BOTH survived validation
        if data.get('start_date') and data.get('end_date'):
            kwargs['start'] = data['start_date']
            kwargs['end'] = data['end_date']
        return kwargs

    def querystring(self):
        """urlencode of non-empty cleaned values. Returns '' when nothing applies."""
        data = self.cleaned_data
        params = {}
        if data.get('q'):
            params['q'] = data['q']
        if data.get('location'):
            params['location'] = data['location']
        if data.get('start_date') and data.get('end_date'):
            params['start_date'] = data['start_date'].isoformat()
            params['end_date'] = data['end_date'].isoformat()
        return urlencode(params) if params else ''
