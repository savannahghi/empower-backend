"""SMS scopes."""
from sil_auth_backends.utilities.utilities import SCOPE_NODE

# SMS

SMS_READ = SCOPE_NODE(
    "advantage.sms.read",
    "View SMSs",
)
SMS_WRITE = SCOPE_NODE(
    "advantage.sms.write",
    "Edit SMSs",
)

# SMS Templates

SMS_TEMPLATE_READ = SCOPE_NODE(
    "advantage.sms_template.read",
    "View SMS templates",
)
SMS_TEMPLATE_WRITE = SCOPE_NODE(
    "advantage.sms_template.write",
    "Edit SMS templates",
)

# SMS Sender IDs

SENDER_ID_READ = SCOPE_NODE(
    "advantage.sender_id.read",
    "View Sender IDs",
)
SENDER_ID_WRITE = SCOPE_NODE(
    "advantage.sender_id.write",
    "Edit Sender IDs",
)
