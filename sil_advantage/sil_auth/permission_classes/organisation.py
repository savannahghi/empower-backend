"""Allow transactions only for users from active organisations."""
from rest_framework import permissions

from sil_advantage.common.types import AuthenticatedRequest


class OrganisationIsActive(permissions.BasePermission):
    """Check if the organisation the user belongs to is activated."""

    message = "Inactive Organisation"

    def has_permission(  # type: ignore
        self,
        request: AuthenticatedRequest,
        view,
    ) -> bool:
        """Return True if the user is linked to an active organisation."""
        user = request.user
        return user.organisation.active
