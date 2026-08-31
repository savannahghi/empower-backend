"""Scheduling settings."""
from typing import List

from sil_advantage.settings.manager import SettingManager

BRANCH_SCHEDULING_SETTINGS: List[SettingManager] = [
    SettingManager(
        "scheduling:appointment_reminder_timings",
        "Hours to send Appointment Reminders",
        [24],  # hours
        list,
    ),
]
ORG_SCHEDULING_SETTINGS = [
    SettingManager(
        "scheduling:appointment_reminder_timings",
        "Hours to send Appointment Reminders",
        [24],  # hours
        list,
    ),
    SettingManager(
        "scheduling:preferred_patient_scheduling_method",
        "Select the preferred patient scheduling method to use",
        "APPOINTMENT BOOKING",
        str,
        lambda x: x in ("APPOINTMENT BOOKING", "CHECK-IN SCHEDULING"),
    ),
    SettingManager(
        "scheduling:appointment_start_visit",
        "Are appointments aimed for starting visits? ",
        True,
        bool,
        None,
    ),
]
