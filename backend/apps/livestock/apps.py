from django.apps import AppConfig


class LivestockConfig(AppConfig):
    name = "apps.livestock"
    verbose_name = "Livestock"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.accounts.signals import farm_created

        from .services import seed_farm_defaults

        def on_farm_created(sender, farm, created_by=None, **kwargs):  # type: ignore[no-untyped-def]
            seed_farm_defaults(farm, created_by)

        farm_created.connect(on_farm_created, dispatch_uid="livestock_seed_defaults", weak=False)
