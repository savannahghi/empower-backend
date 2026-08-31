"""Auth URLs."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from sil_advantage.sil_auth.views import (
    PermissionListView,
    RoleListCreateView,
    RolePermissionRetrieveUpdateView,
    RolePermissionsListCreateView,
    RoleRetrieveUpdateView,
    UserListCreateView,
    UserMFAViewSet,
    UserRetrieveUpdateView,
)

router = SimpleRouter()

router.register("users-mfa", UserMFAViewSet)

urlpatterns = router.urls
urlpatterns += (
    # roles & permissions
    path(
        "permissions/",
        PermissionListView.as_view(),
        name="permission-list",
    ),
    path(
        "roles/",
        RoleListCreateView.as_view(),
        name="role-list",
    ),
    path(
        "roles/<str:pk>/",
        RoleRetrieveUpdateView.as_view(),
        name="role-detail",
    ),
    path(
        "role_permissions/",
        RolePermissionsListCreateView.as_view(),
        name="rolepermissions-list",
    ),
    path(
        "role_permissions/<str:pk>/",
        RolePermissionRetrieveUpdateView.as_view(),
        name="rolepermissions-detail",
    ),
    # users
    path(
        "users/",
        UserListCreateView.as_view(),
        name="user-list",
    ),
    path(
        "users/<str:guid>/",
        UserRetrieveUpdateView.as_view(),
        name="user-detail",
    ),
)
