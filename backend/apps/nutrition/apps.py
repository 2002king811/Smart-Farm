from django.apps import AppConfig


class NutritionConfig(AppConfig):
    name = "apps.nutrition"
    verbose_name = "Nutrition and feeding"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.accounts.signals import farm_created

        from . import services

        def on_farm_created(sender, farm, created_by=None, **kwargs):  # type: ignore[no-untyped-def]
            services.seed_feed_items(farm)

        farm_created.connect(on_farm_created, dispatch_uid="nutrition_seed_feed", weak=False)
