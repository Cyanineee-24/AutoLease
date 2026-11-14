from django.apps import AppConfig


class UserprofileConfig(AppConfig):
    name = 'apps.userprofile'

    def ready(self):
        from . import signals  # noqa: F401  (connects the post_save receiver)
