from django.conf import settings
from django.db import migrations


def backfill_profiles(apps, schema_editor):
    """Create a Profile for every user that doesn't have one yet. Safe to re-run."""
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    Profile = apps.get_model('userprofile', 'Profile')
    has_profile = Profile.objects.values('user_id')
    missing = User.objects.exclude(pk__in=has_profile).values_list('pk', flat=True)
    Profile.objects.bulk_create(
        [Profile(user_id=user_id) for user_id in missing],
        batch_size=500,
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('userprofile', '0002_driverlicense'),
        ('accounts', '0002_customuser_contact_number'),
    ]

    operations = [
        migrations.RunPython(backfill_profiles, migrations.RunPython.noop),
    ]
