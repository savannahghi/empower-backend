"""URL patterns for the test app."""
from django.urls import path

from .views import CustomMetaView, MtoMCustomMetaView, TestCustomView

urlpatterns = (
    path("custom_meta/", CustomMetaView.as_view(), name="custom_meta"),
    path(
        "my_custom_meta/",
        MtoMCustomMetaView.as_view(),
        name="my_custom_meta",
    ),
    path("test_custom/", TestCustomView.as_view(), name="test_custom"),
)
