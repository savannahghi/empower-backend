"""Scheduling scopes."""
from sil_auth_backends.utilities.utilities import SCOPE_NODE

# Schedules

SCHEDULE_READ = SCOPE_NODE(
    "advantage.schedule.read",
    "View schedules",
)
SCHEDULE_WRITE = SCOPE_NODE(
    "advantage.schedule.write",
    "Edit schedules",
)


# Slots

SLOT_READ = SCOPE_NODE(
    "advantage.slot.read",
    "View slots",
)
SLOT_WRITE = SCOPE_NODE(
    "advantage.slot.write",
    "Edit slots",
)


# Appointments

APPOINTMENT_READ = SCOPE_NODE(
    "advantage.appointment.read",
    "View appointments",
)
APPOINTMENT_WRITE = SCOPE_NODE(
    "advantage.appointment.write",
    "Edit appointments",
)
