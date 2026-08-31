"""SMS permissions."""
from sil_auth_backends.utilities.utilities import PERM_NODE

# SMS

SMS_VIEW = PERM_NODE(
    "advantage.sms_list",
    "View SMS",
)

SMS_CREATE = PERM_NODE(
    "advantage.sms_create",
    "Create SMS",
)

SMS_BROADCAST = PERM_NODE(
    "advantage.sms_broadcast",
    "Broadcast SMS",
)


# SMS Templates

SMS_TEMPLATE_VIEW = PERM_NODE(
    "advantage.sms_template_list",
    "View SMS templates",
)

SMS_TEMPLATE_CREATE = PERM_NODE(
    "advantage.sms_template_create",
    "Create SMS templates",
)

SMS_TEMPLATE_EDIT = PERM_NODE(
    "advantage.sms_template_edit",
    "Edit SMS templates",
)

SMS_TEMPLATE_DELETE = PERM_NODE(
    "advantage.sms_template_delete",
    "Remove SMS templates",
)

# SMS Sender IDs

SENDER_ID_VIEW = PERM_NODE(
    "advantage.sender_id_list",
    "View sender IDs",
)

SENDER_ID_CREATE = PERM_NODE(
    "advantage.sender_id_create",
    "Create Sender IDs",
)

SENDER_ID_EDIT = PERM_NODE(
    "advantage.sender_id_edit",
    "Edit Sender IDs",
)

SENDER_ID_DELETE = PERM_NODE(
    "advantage.sender_id_delete",
    "Remove Sender IDs",
)
