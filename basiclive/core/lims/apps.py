from django.apps import AppConfig


class LimsConfig(AppConfig):
    name = "basiclive.core.lims"
    app_label = "lims"
    verbose_name = "LIMS"

    def ready(self):
        from . import signals  # noqa: F401
