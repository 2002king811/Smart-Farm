from django.apps import AppConfig


class BreedingConfig(AppConfig):
    name = "apps.breeding"
    verbose_name = "Breeding and kids"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from . import services  # noqa: F401  (registers the timeline source)
