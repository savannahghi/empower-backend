"""Grant special override permission for network admins."""
from rest_framework import permissions

from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.permissions import perms as perms


class IsNetworkAdmin(permissions.BasePermission):
    """Check if the user is a network admin and allow access."""

    def has_permission(  # type: ignore
        self,
        request: AuthenticatedRequest,
        view,
    ) -> bool:
        """Return True if the user is a network admin."""
        self.message = (
            "Permission denied: You must be a network administrator"
            " to perform this action"
        )
        user = request.user
        return user.has_permissions([perms.CROSS_NETWORK_ADMIN[0]])
