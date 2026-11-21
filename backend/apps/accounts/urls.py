from django.urls import path

from .views import MeView, MyFarmsView

urlpatterns = [
    path("me", MeView.as_view(), name="me"),
    path("me/farms", MyFarmsView.as_view(), name="me-farms"),
]
