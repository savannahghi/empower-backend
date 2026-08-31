"""Scheduling filters."""
from django_filters.filters import DateFilter

from sil_advantage.common.filters.base import CommonFieldsFilterset, ListFilter
from sil_advantage.common.filters.common_filters import AllDateTimeFilter
from sil_advantage.scheduling.models import (
    Appointment,
    Schedule,
    ScheduleTiming,
    Slot,
)


class ScheduleFilter(CommonFieldsFilterset):
    """Filter schedules."""

    specialty = ListFilter()
    actor = ListFilter()

    class Meta:
        """Filter options."""

        model = Schedule
        fields = "__all__"


class ScheduleTimingFilter(CommonFieldsFilterset):
    """Filter schedule timings."""

    class Meta:
        """Filter options."""

        model = ScheduleTiming
        fields = "__all__"


class SlotFilter(CommonFieldsFilterset):
    """Filter slots."""

    schedule_id = ListFilter(field_name="schedule__id", lookup_expr="in")
    start = DateFilter(field_name="start", lookup_expr="date")
    end = DateFilter(field_name="end", lookup_expr="date")
    from_date = AllDateTimeFilter(field_name="start", lookup_expr="gte")
    to_date = AllDateTimeFilter(field_name="start", lookup_expr="lte")
    status = ListFilter()

    class Meta:
        """Filter options."""

        model = Slot
        fields = "__all__"


class AppointmentFilter(CommonFieldsFilterset):
    """Filter appointments."""

    start = DateFilter(field_name="start", lookup_expr="date")
    end = DateFilter(field_name="end", lookup_expr="date")
    from_date = AllDateTimeFilter(field_name="start", lookup_expr="gte")
    to_date = AllDateTimeFilter(field_name="start", lookup_expr="lte")
    schedule_id = ListFilter(
        field_name="slot__schedule__id",
        lookup_expr="in",
    )
    schedule_actor = ListFilter(
        field_name="slot__schedule__actor",
        lookup_expr="in",
    )
    appointment_status = ListFilter()

    class Meta:
        """Filter options."""

        model = Appointment
        exclude = ("pending_reminders",)
