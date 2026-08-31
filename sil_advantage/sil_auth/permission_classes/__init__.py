"""Assemble authentication permission classes."""
from sil_advantage.sil_auth.permission_classes.base import (
    ViewBasePermission,
    WriteOnlyPermission,
)
from sil_advantage.sil_auth.permission_classes.is_network_admin import (
    IsNetworkAdmin,
)
from sil_advantage.sil_auth.permission_classes.organisation import (
    OrganisationIsActive,
)

__all__ = [
    "OrganisationIsActive",
    "IsNetworkAdmin",
    "ViewBasePermission",
    "WriteOnlyPermission",
]
