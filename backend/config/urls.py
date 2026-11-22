from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core import health

admin.site.site_header = "Smart Farm platform admin"
admin.site.site_title = "Smart Farm admin"

urlpatterns = [
    path("api/health/live", health.live, name="health-live"),
    path("api/health", health.ready, name="health"),
    path("api/v1/", include("config.api_v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path(settings.ADMIN_URL, admin.site.urls),
]

if settings.DEBUG and settings.MESSAGING_ADAPTER == "console":
    from apps.notifications.dev_views import outbox

    urlpatterns.insert(0, path("api/dev/outbox", outbox, name="dev-outbox"))

if settings.DEBUG and not settings.USE_S3:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
