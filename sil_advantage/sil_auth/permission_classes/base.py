"""Base permissions."""
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from sil_auth_backends.utilities.utilities import PERM_NODE

from sil_advantage.common.types import AuthenticatedRequest


class ViewBasePermission(BasePermission):
    """Enforce viewset permissions."""

    def _process_perms(self, nested_perms: list[PERM_NODE]) -> list[str]:
        """Process and flatten permissions."""
        perms = []
        for perm in nested_perms:
            perms.append(perm.name)
            perms.extend(self._process_perms(perm.children))
        return perms

    def _get_method_perms(
        self,
        view_perms: dict[str, list[PERM_NODE]],
        method: str,
    ) -> list[str]:
        """Get permissions set for a method."""
        method_perms = view_perms.get(method, None)
        return self._process_perms(method_perms or [])

    def has_permission(  # type: ignore
        self,
        request: AuthenticatedRequest,
        view,
    ) -> bool:
        """Enforce view permissions."""
        view_perms = view.permissions
        get_perms = view_perms.get("GET", [])
        view_perms.update(
            {
                "PUT": view_perms.get("PATCH", []),
                "OPTIONS": get_perms,
                "HEAD": get_perms,
                "TRACE": get_perms,
            }
        )
        assert request.method is not None
        method_perms = self._get_method_perms(
            view.permissions,
            request.method.upper(),
        )
        return request.user.has_permissions(method_perms)


class WriteOnlyPermission(BasePermission):
    """Write only permission."""

    def has_permission(self, request: Request, view) -> bool:  # type: ignore
        """Check if the request method is POST."""
        assert request.method is not None
        return request.method.upper() in ("POST", "OPTIONS")
