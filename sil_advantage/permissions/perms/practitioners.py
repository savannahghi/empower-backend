"""Practitioners permissions."""
from sil_auth_backends.utilities.utilities import PERM_NODE

PRACTITIONER_VIEW = PERM_NODE(
    "advantage.practitioner_list",
    "View practitioners",
)

PRACTITIONER_CREATE = PERM_NODE(
    "advantage.practitioner_create",
    "Create practitioners",
)

PRACTITIONER_EDIT = PERM_NODE(
    "advantage.practitioner_edit",
    "Edit practitioners",
)

PRACTITIONER_DELETE = PERM_NODE(
    "advantage.practitioner_delete",
    "Remove practitioners",
)
