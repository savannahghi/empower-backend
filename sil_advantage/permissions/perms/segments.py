"""Segments permissions."""

from sil_auth_backends.utilities.utilities import PERM_NODE

SEGMENT_VIEW = PERM_NODE(
    "advantage.segment_list",
    "View person segments",
)

SEGMENT_CREATE = PERM_NODE(
    "advantage.segment_create",
    "Create person segments",
)

SEGMENT_EDIT = PERM_NODE(
    "advantage.segment_edit",
    "Edit person segments",
)

SEGMENT_DELETE = PERM_NODE(
    "advantage.segment_delete",
    "Remove person segments",
)

MESSAGE_TEMPLATE_VIEW = PERM_NODE(
    "advantage.message_template_list",
    "View person message templates",
)

MESSAGE_TEMPLATE_CREATE = PERM_NODE(
    "advantage.message_template_create",
    "Create person message templates",
)

MESSAGE_TEMPLATE_EDIT = PERM_NODE(
    "advantage.message_template_edit",
    "Edit person message templates",
)

MESSAGE_TEMPLATE_DELETE = PERM_NODE(
    "advantage.message_template_delete",
    "Remove person message templates",
)
