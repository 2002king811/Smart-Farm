from django.urls import include, path

from apps.core.routers import Router
from config.urls import urlpatterns as project_urlpatterns
from tests.testapp.views import GoatViewSet, PenViewSet

test_router = Router()
test_router.register("test-goats", GoatViewSet, basename="test-goat")
test_router.register("test-pens", PenViewSet, basename="test-pen")

urlpatterns = [path("api/v1/", include(test_router.urls)), *project_urlpatterns]
