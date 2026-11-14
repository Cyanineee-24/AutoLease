from django.conf import settings
from django.db import migrations


def backfill_usersettings(apps, schema_editor):
    """Create a UserSettings row (model defaults) for every user without one. Safe to re-run."""
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    UserSettings = apps.get_model('usersettings', 'UserSettings')
    has_settings = UserSettings.objects.values('user_id')
    missing = User.objects.exclude(pk__in=has_settings).values_list('pk', flat=True)
    UserSettings.objects.bulk_create(
        [
            UserSettings(
                user_id=user_id,
                email_notifications=True,
                marketing_emails=True,
                sms_notifications=False,
                show_contact_number=True,
            )
            for user_id in missing
        ],
        batch_size=500,
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('usersettings', '0002_usersettings_marketing_emails_and_more'),
        ('accounts', '0002_customuser_contact_number'),
    ]

    operations = [
        migrations.RunPython(backfill_usersettings, migrations.RunPython.noop),
    ]
