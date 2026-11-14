from django.apps import AppConfig


class UsersettingsConfig(AppConfig):
    name = 'apps.usersettings'

    def ready(self):
        from . import signals  # noqa: F401  (connects the post_save receiver)
