from django.apps import AppConfig


class TestAppConfig(AppConfig):
    """Test-only farm-scoped models that exercise the tenancy base classes."""

    name = "tests.testapp"
    label = "testapp"
    default_auto_field = "django.db.models.BigAutoField"
