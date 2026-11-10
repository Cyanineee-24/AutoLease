from django import forms


class DecisionForm(forms.Form):
    ACTION_CHOICES = [('approve', 'Approve'), ('decline', 'Decline')]

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    agency_response = forms.CharField(required=False, max_length=1000, strip=True)
