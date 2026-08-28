"""Shortcuts grouping detailed permissions into detailed groups."""
from sil_auth_backends.utilities.utilities import PERM_NODE

from sil_advantage.permissions.perms import common

_BRANCH_ADMIN = "auth.is_branch_level"
_CLUSTER_ADMIN = "auth.is_cluster_level"
_ORGANISATION_ADMIN = "auth.is_organisation_level"
_NETWORK_ADMIN = "auth.is_network_level"
_CROSS_NETWORK_ADMIN = "auth.is_cross_network_level"
_BP_VIEW = "auth.bp_view"
_PERMS_USER_MGMT = [
    "auth.user_view",
    "auth.user_create",
    "auth.user_edit",
    "auth.user_remove",
    "auth.permission_view",
    "auth.role_view",
    "auth.role_create",
    "auth.role_edit",
    "auth.role_delete",
]
_AUTH_ORG_ADMIN = [_ORGANISATION_ADMIN]

_AUTH_ORG_ADMIN += _PERMS_USER_MGMT
ORG_ADMIN = [
    common.ORGANISATION_VIEW,
    common.ORGANISATION_EDIT,
    common.PERSON_VIEW,
    common.PERSON_CREATE,
    common.PERSON_EDIT,
    common.PERSON_DELETE,
]

ORG_ADMIN += _AUTH_ORG_ADMIN


BRANCH_ADMIN_PERMS = [
    _BRANCH_ADMIN,
]

CLUSTER_ADMIN_PERMS = [
    _CLUSTER_ADMIN,
]

NETWORK_ADMIN_PERMS = [
    _NETWORK_ADMIN,
    common.ORGANISATION_VIEW,
    common.ORGANISATION_EDIT,
    common.ORGANISATION_DELETE,
    common.ORGANISATION_CREATE,
    _BP_VIEW,
]

NETWORK_ADMIN_PERMS += _PERMS_USER_MGMT

CROSS_NETWORK_ADMIN_PERMS = [_CROSS_NETWORK_ADMIN]

CROSS_NETWORK_ADMIN_PERMS += NETWORK_ADMIN_PERMS


BRANCH_ADMIN_PERMS += _PERMS_USER_MGMT

CLUSTER_ADMIN_PERMS += BRANCH_ADMIN_PERMS

ORGANISATION_ADMIN = PERM_NODE(
    "erp.is_organisation_level",
    "Organisation Admin permission",
    children=tuple(ORG_ADMIN),
)

BRANCH_ADMIN = PERM_NODE(
    "erp.is_branch_level",
    "Branch Admin permission",
    children=tuple(BRANCH_ADMIN_PERMS),
)

CLUSTER_ADMIN = PERM_NODE(
    "erp.is_cluster_level",
    "Cluster Admin permission",
    children=tuple(CLUSTER_ADMIN_PERMS),
)

CROSS_NETWORK_ADMIN = PERM_NODE(
    "erp.is_cross_network_level",
    "Network Admin permission",
    children=tuple(CROSS_NETWORK_ADMIN_PERMS),
)
