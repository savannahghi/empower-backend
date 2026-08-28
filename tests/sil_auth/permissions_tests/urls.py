"""URL config for permissions test."""
from django.urls import path

from tests.sil_auth.permissions_tests.views import (
    NoPermsListView,
    TestListView,
    TestOrgListView,
)

urlpatterns = (
    path("test_org/", TestOrgListView.as_view(), name="test_org"),
    path("test_lisr/", TestListView.as_view(), name="test_list"),
    path("no_perms/", NoPermsListView.as_view(), name="no_perms"),
)
