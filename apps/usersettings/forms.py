from django import forms

from .models import UserSettings

# Each setting renders as an on/off switch: still a checkbox, so it submits
# and works with the keyboard as before; role="switch" tells screen readers.
SWITCH_ATTRS = {'class': 'switch', 'role': 'switch'}


class UserSettingsForm(forms.ModelForm):
    class Meta:
        model = UserSettings
        fields = ['email_notifications', 'marketing_emails', 'sms_notifications', 'show_contact_number']
        widgets = {field: forms.CheckboxInput(attrs=SWITCH_ATTRS) for field in fields}
