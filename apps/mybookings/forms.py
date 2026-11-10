from django import forms

from apps.bookings.models import Review


class ReviewForm(forms.ModelForm):
    RATING_CHOICES = [(5, '5'), (4, '4'), (3, '3'), (2, '2'), (1, '1')]

    rating = forms.TypedChoiceField(
        choices=RATING_CHOICES,
        coerce=int,
        widget=forms.RadioSelect,
        error_messages={'required': 'Pick a star rating.'},
    )
    comment = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'How was the car and the pick-up?'}),
    )

    class Meta:
        model = Review
        fields = ['rating', 'comment']
