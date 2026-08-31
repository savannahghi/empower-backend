"""Notifications permissions."""

from sil_auth_backends.utilities.utilities import PERM_NODE

# Message Groups

GROUP_VIEW = PERM_NODE(
    "advantage.group_list",
    "View message groups",
)

GROUP_CREATE = PERM_NODE(
    "advantage.group_create",
    "Create message groups",
)

GROUP_EDIT = PERM_NODE(
    "advantage.group_edit",
    "Edit message groups",
)

GROUP_DELETE = PERM_NODE(
    "advantage.group_delete",
    "Remove message groups",
)
