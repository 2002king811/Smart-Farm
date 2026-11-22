from django.apps import AppConfig


class HealthConfig(AppConfig):
    name = "apps.health"
    verbose_name = "Animal health"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.accounts.signals import farm_created

        from . import services  # registers the timeline source

        def on_farm_created(sender, farm, created_by=None, **kwargs):  # type: ignore[no-untyped-def]
            services.seed_catalogs(farm)

        farm_created.connect(on_farm_created, dispatch_uid="health_seed_catalogs", weak=False)
