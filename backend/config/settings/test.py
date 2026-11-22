import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-for-production-use-0123456789")
os.environ.setdefault("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/smartfarm_test")

from .base import *  # noqa: F403

APP_ENV = "test"
DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MESSAGING_ADAPTER = SMS_ADAPTER = WHATSAPP_ADAPTER = "console"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
LOGGING["handlers"]["console"]["formatter"] = "text"  # type: ignore[index] # noqa: F405

INSTALLED_APPS = [*INSTALLED_APPS, "tests.testapp"]  # noqa: F405
ROOT_URLCONF = "tests.urls"
RUN_ON_COMMIT_IMMEDIATELY = True
JWT_COOKIE_SECURE = False
