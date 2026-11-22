from django.urls import path

from apps.notifications.consumers import NotificationConsumer

from .consumers import HealthConsumer

websocket_urlpatterns = [
    path("ws/health", HealthConsumer.as_asgi()),
    path("ws/notifications", NotificationConsumer.as_asgi()),
]
