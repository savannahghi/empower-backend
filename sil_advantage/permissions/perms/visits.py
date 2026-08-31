"""Visits permissions."""
from sil_auth_backends.utilities.utilities import PERM_NODE

# Visits

VISIT_VIEW = PERM_NODE(
    "advantage.visit_list",
    "View visits",
)

VISIT_CREATE = PERM_NODE(
    "advantage.visit_create",
    "Create visits",
)

VISIT_EDIT = PERM_NODE(
    "advantage.visit_edit",
    "Edit visits",
)

VISIT_DELETE = PERM_NODE(
    "advantage.visit_delete",
    "Remove visits",
)

VISIT_COMPLETE = PERM_NODE(
    "advantage.visit_complete",
    "Complete visits",
)

VISIT_COMPLETE_UNPAID = PERM_NODE(
    "advantage.visit_complete_unpaid",
    "Complete unpaid visits",
)


# Queues

QUEUE_VIEW = PERM_NODE(
    "advantage.queue_list",
    "View queues",
)

QUEUE_CREATE = PERM_NODE(
    "advantage.queue_create",
    "Create queues",
)

QUEUE_EDIT = PERM_NODE(
    "advantage.queue_edit",
    "Edit queues",
)

QUEUE_DELETE = PERM_NODE(
    "advantage.queue_delete",
    "Remove queues",
)
