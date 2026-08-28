"""Scheduling permissions."""
from sil_auth_backends.utilities.utilities import PERM_NODE

# Schedules

SCHEDULE_VIEW = PERM_NODE(
    "advantage.schedule_list",
    "View schedules",
)

SCHEDULE_CREATE = PERM_NODE(
    "advantage.schedule_create",
    "Create schedules",
)

SCHEDULE_EDIT = PERM_NODE(
    "advantage.schedule_edit",
    "Edit schedules",
)

SCHEDULE_DELETE = PERM_NODE(
    "advantage.schedule_delete",
    "Remove schedules",
)


# Slots

SLOT_VIEW = PERM_NODE(
    "advantage.slot_list",
    "View slots",
)

SLOT_CREATE = PERM_NODE(
    "advantage.slot_create",
    "Create slots",
)

SLOT_EDIT = PERM_NODE(
    "advantage.slot_edit",
    "Edit slots",
)

SLOT_DELETE = PERM_NODE(
    "advantage.slot_delete",
    "Remove slots",
)


# Appointments

APPOINTMENT_VIEW = PERM_NODE(
    "advantage.appointment_list",
    "View appointments",
)

APPOINTMENT_CREATE = PERM_NODE(
    "advantage.appointment_create",
    "Create appointments",
)

APPOINTMENT_EDIT = PERM_NODE(
    "advantage.appointment_edit",
    "Edit appointments",
)

APPOINTMENT_DELETE = PERM_NODE(
    "advantage.appointment_delete",
    "Remove appointments",
)
