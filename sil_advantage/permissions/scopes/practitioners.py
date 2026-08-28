"""Practitioner scopes."""
from sil_auth_backends.utilities.utilities import SCOPE_NODE

PRACTITIONER_READ = SCOPE_NODE(
    "advantage.practitioner.read",
    "View practitioners",
)
PRACTITIONER_WRITE = SCOPE_NODE(
    "advantage.practitioner.write",
    "Edit practitioners",
)
