from django import forms


class DecisionForm(forms.Form):
    ACTION_CHOICES = [('approve', 'Approve'), ('decline', 'Decline')]

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    agency_response = forms.CharField(required=False, max_length=1000, strip=True)


class CancelTripForm(forms.Form):
    reason = forms.CharField(
        max_length=1000,
        strip=True,
        error_messages={
            'required': "Tell the renter why you're cancelling.",
            'max_length': 'Keep the reason to 1000 characters or fewer.',
        },
    )
