"""Visits scopes."""
from sil_auth_backends.utilities.utilities import SCOPE_NODE

# Visits

VISIT_READ = SCOPE_NODE(
    "advantage.visit.read",
    "View visits",
)
VISIT_WRITE = SCOPE_NODE(
    "advantage.visit.write",
    "Edit visits",
)


# Queues

QUEUE_READ = SCOPE_NODE(
    "advantage.queue.read",
    "View queues",
)
QUEUE_WRITE = SCOPE_NODE(
    "advantage.queue.write",
    "Edit queues",
)
