"""Notifications scopes."""
from sil_auth_backends.utilities.utilities import SCOPE_NODE

# Message Groups

GROUP_READ = SCOPE_NODE(
    "advantage.message.read",
    "View message groups",
)
GROUP_WRITE = SCOPE_NODE(
    "advantage.message.write",
    "Edit message groups",
)
