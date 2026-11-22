from django.apps import AppConfig


class CalendarConfig(AppConfig):
    name = "apps.calendar"
    verbose_name = "Health calendar"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.accounts.signals import farm_created

        from .services import seed_categories

        def on_farm_created(sender, farm, created_by=None, **kwargs):  # type: ignore[no-untyped-def]
            seed_categories(farm)

        farm_created.connect(on_farm_created, dispatch_uid="calendar_seed_categories", weak=False)
