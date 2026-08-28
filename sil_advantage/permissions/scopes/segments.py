"""Segments scopes."""
from sil_auth_backends.utilities.utilities import SCOPE_NODE

SEGMENT_READ = SCOPE_NODE(
    "advantage.segment.read",
    "View person segments",
)
SEGMENT_WRITE = SCOPE_NODE(
    "advantage.segment.write",
    "Edit person segments",
)

MESSAGE_TEMPLATE_READ = SCOPE_NODE(
    "advantage.message_template.read",
    "View person message templates",
)
MESSAGE_TEMPLATE_WRITE = SCOPE_NODE(
    "advantage.message_template.write",
    "Edit person message templates",
)
