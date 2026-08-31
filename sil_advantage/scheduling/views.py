"""Scheduling views."""
import calendar
from datetime import datetime, timedelta
from typing import Any, Sequence
from uuid import UUID

import pytz
from dateutil.parser import parse as parse_date
from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from fuzzywuzzy import process
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.common.views.base import CacheableBaseView
from sil_advantage.permissions import perms, scopes
from sil_advantage.scheduling import (
    PRACTITIONER_TYPES,
    SLOT_STATUS,
    filters,
    models,
    serializers,
)


def normalize_to_start_of_day(date_param: datetime) -> datetime:
    """Force an input timestamp to the start of its day."""
    normalized_start = datetime(
        year=date_param.year,
        month=date_param.month,
        day=date_param.day,
    )
    local_tz = pytz.timezone(settings.TIME_ZONE)
    normalized_start = normalized_start.astimezone(local_tz)
    return normalized_start.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


class ScheduleView(CacheableBaseView):
    """Schedule viewset."""

    permissions = {
        "GET": [perms.SCHEDULE_VIEW],
        "POST": [perms.SCHEDULE_CREATE],
        "PATCH": [perms.SCHEDULE_EDIT],
        "DELETE": [perms.SCHEDULE_DELETE],
    }
    scopes = {
        "GET": [scopes.SCHEDULE_READ],
        "POST": [scopes.SCHEDULE_WRITE],
        "PATCH": [scopes.SCHEDULE_WRITE],
        "DELETE": [scopes.SCHEDULE_WRITE],
    }

    queryset = models.Schedule.objects.all().prefetch_related("timings")
    _select_related = ["queue", "practitioner"]

    serializer_class = serializers.ScheduleSerializer
    filterset_class = filters.ScheduleFilter
    ordering_fields = ("updated",)
    search_fields = ("description",)

    _data_partition_field = "branch_id"

    def _create_timings(
        self,
        schedule: models.Schedule,
        availability: dict[str, list[dict[str, str]]],
        base_defaults: dict[str, Any],
    ) -> None:
        """Create timings."""
        timing_instances: list[models.ScheduleTiming] = []
        seen_timings: dict[str, list[int]] = {str(i): [] for i in range(8)}
        for day, timings in availability.items():
            for timing in timings:
                start = parse_date(timing["start"])
                end = parse_date(timing["end"])
                timing_instance = models.ScheduleTiming(
                    day_of_week=day,
                    start=timing["start"],
                    end=timing["end"],
                    schedule=schedule,
                    **base_defaults,
                )
                timing_instance.clean()
                start_mins = start.hour * 60 + start.minute
                end_mins = end.hour * 60 + end.minute
                if start_mins in seen_timings[day] or end_mins in seen_timings[day]:
                    raise ValidationError(
                        _(f"Availability on {calendar.day_name[int(day)]} overlaps.")
                    )
                timing_instances.append(timing_instance)
                seen_timings[day].extend(range(start_mins, end_mins))
        models.ScheduleTiming.objects.bulk_create(timing_instances)

    @transaction.atomic()
    def create(self, request: AuthenticatedRequest) -> Response:
        """Create a new schedule.

        Payload format:
        {
            "description": "Dr. Jane Doe",
            "specialty": "GENERAL PRACTITIONER",
            "slot_duration": 30,
            "availability": {
                '0': [{"start": "08:00", "end": "17:00"}],  # 0 is Monday
                '1': [{"start": "14:00", "end": "17:00"}],
                '2': [{"start": "08:00", "end": "17:00"}],
                '3': [
                    {"start": "08:00", "end": "12:00"},
                    {"start": "14:00", "end": "17:00"}
                ],
                '5': [],
                '6': [{"start": "10:00", "end": "12:00"}],
            }
        }
        """
        payload = request.data

        org = request.user.organisation
        sched_serializer = serializers.ScheduleSerializer(
            data=payload, context={"request": request}
        )
        sched_serializer.is_valid()
        base_defaults = {
            "organisation": org,
            "created_by": request.user.guid,
            "updated_by": request.user.guid,
        }
        schedule = sched_serializer.save(**base_defaults)
        self._create_timings(schedule, payload["availability"], base_defaults)

        serialized_schedule = serializers.ScheduleSerializer(schedule).data
        return Response(
            serialized_schedule,
            status=status.HTTP_201_CREATED,
        )

    def _update_availability(
        self,
        schedule: models.Schedule,
        updated_availability: dict[str, list[dict[str, str]]],
        request: AuthenticatedRequest,
    ) -> None:
        """Update schedule availability."""
        if updated_availability is None:
            return

        # Delete unused slots 🙂
        for timing in schedule.timings.all():
            unused_slots = schedule.schedule_slots.filter(
                start__iso_week_day=int(timing.day_of_week) + 1,
                start__time__gte=timing.start,
                end__time__lte=timing.end,
                status=SLOT_STATUS.FREE,
                slot_appointments__isnull=True,
            )
            unused_slots.delete()

        # update availability
        # Deleting here since ScheduleTimings aren't related
        # to any other objects so we only lose
        # creation metadata
        # This is a tradeoff to doing a diff between
        # the incoming and what's in the DB.
        # The latter is more prone to bugs
        schedule.timings.all().delete()  # 🫠
        base_defaults = {
            "organisation": request.user.organisation,
            "created_by": request.user.guid,
            "updated_by": request.user.guid,
            "cluster_id": schedule.cluster_id,
            "branch_id": schedule.branch_id,
            "department_id": schedule.department_id,
            "workstation_id": schedule.workstation_id,
        }
        self._create_timings(schedule, updated_availability, base_defaults)

    def update(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Update a Schedule and its availability."""
        schedule = self.get_object()
        availability = request.data.get("availability", None)
        self._update_availability(schedule, availability, request)
        return super().update(request, *args, **kwargs)

    def partial_update(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Partial update a Schedule and its availability."""
        schedule = self.get_object()
        availability = request.data.get("availability", None)
        self._update_availability(schedule, availability, request)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["GET"])
    def cancel_day_appts(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Cancel the day's appointments that are still BOOKED.

        This is NOT a pure GET as it modifies appointments on the server.
        """
        date_param = request.GET.get("date", None)
        if date_param is None:
            raise ValidationError(_("Please provide a date."))

        schedule = self.get_object()
        date = parse_date(date_param)
        slots = schedule.schedule_slots.filter(
            start__date=date, start__gt=timezone.now()
        ).prefetch_related(
            Prefetch(
                "slot_appointments",
                queryset=models.Appointment.objects.filter(appointment_status="BOOKED"),
                to_attr="booked_appts",
            )
        )

        for slot in slots:
            for appt in slot.booked_appts:
                appt.appointment_status = "CANCELLED"
                appt.save(update_fields=["appointment_status"])

        return Response("OK", status=status.HTTP_200_OK)

    @action(detail=False, methods=["GET"])
    def specialties(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Provide endpoint to list and search through the list of specialties.

        This endpoint can be hit without the search param and will return all
        available specialties. The search param is provided via "?search=Practitioner".
        This uses a case insensitive search.
        """
        search_param = request.GET.get("search", None)
        specialties = [specialty[0] for specialty in PRACTITIONER_TYPES]
        if search_param:
            matches = process.extract(search_param, specialties, limit=25)
            matches.sort(key=lambda x: (-x[1], len(x[0])))
            specialties = [match[0] for match in matches if match[1] > 80]
        else:
            specialties.sort(key=lambda x: len(x))
        return Response(specialties, status=status.HTTP_200_OK)

    @action(detail=True, methods=["GET"])
    def block_slots(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Block slots for a given date or dates , or specific hours of a day."""
        date_param = request.GET.get("date", None)
        end_date_param = request.GET.get("end_date", None)
        start_time_param = request.GET.get("start_time", None)
        end_time_param = request.GET.get("end_time", None)

        if date_param is None:
            raise ValidationError("Please provide a date.")

        schedule_id = self.kwargs["pk"]

        schedule = self.get_queryset().get(pk=schedule_id)
        date = parse_date(date_param)
        end_date = parse_date(end_date_param) if end_date_param else date
        if end_date < date:
            raise ValidationError("End date cannot be earlier than start date.")

        if start_time_param and end_time_param:
            start_time = datetime.strptime(start_time_param, "%H:%M:%S").time()
            end_time = datetime.strptime(end_time_param, "%H:%M:%S").time()
            slots = schedule.schedule_slots.filter(
                start__date__range=[date, end_date],
                start__time__gte=start_time,
                end__time__lte=end_time,
                start__gt=timezone.now(),
            )
        else:
            slots = schedule.schedule_slots.filter(
                start__date__range=[date, end_date], start__gt=timezone.now()
            )

        slots.update(status=SLOT_STATUS.BUSY_UNAVAILABLE)

        return Response(
            {"detail": _("Slots for the date have been blocked.")}, status=200
        )

    @action(detail=True, methods=["GET"])
    def unblock_slots(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Unblock all slots for given date,dates or specific hours of a day."""
        date_param = request.GET.get("date", None)
        end_date_param = request.GET.get("end_date", None)
        start_time_param = request.GET.get("start_time", None)
        end_time_param = request.GET.get("end_time", None)

        if date_param is None:
            raise ValidationError("Please provide a date.")

        schedule_id = self.kwargs["pk"]

        schedule = self.get_queryset().get(pk=schedule_id)
        date = parse_date(date_param)
        end_date = parse_date(end_date_param) if end_date_param else date

        if start_time_param and end_time_param:
            start_time = datetime.strptime(start_time_param, "%H:%M:%S").time()
            end_time = datetime.strptime(end_time_param, "%H:%M:%S").time()
            slots = schedule.schedule_slots.filter(
                start__date__range=[date, end_date],
                start__time__gte=start_time,
                end__time__lte=end_time,
                start__gt=timezone.now(),
            )
        else:
            slots = schedule.schedule_slots.filter(
                start__date__range=[date, end_date], start__gt=timezone.now()
            )

        slots.update(status=SLOT_STATUS.FREE)

        return Response(
            {"detail": _("Slots for the date have been unblocked.")}, status=200
        )


class ScheduleTimingView(CacheableBaseView):
    """Schedule Timings viewset."""

    permissions = {
        "GET": [perms.SCHEDULE_VIEW],
        "POST": [perms.SCHEDULE_CREATE],
        "PATCH": [perms.SCHEDULE_EDIT],
        "DELETE": [perms.SCHEDULE_DELETE],
    }
    scopes = {
        "GET": [scopes.SCHEDULE_READ],
        "POST": [scopes.SCHEDULE_WRITE],
        "PATCH": [scopes.SCHEDULE_WRITE],
        "DELETE": [scopes.SCHEDULE_WRITE],
    }
    queryset = models.ScheduleTiming.objects.all()
    serializer_class = serializers.ScheduleTimingSerializer
    ordering_fields = ("start",)
    filterset_class = filters.ScheduleTimingFilter
    search_fields: Sequence[str] = []

    _data_partition_field = "branch_id"


class SlotView(CacheableBaseView):
    """Slots viewset."""

    permissions = {
        "GET": [perms.SLOT_VIEW],
        "POST": [perms.SLOT_CREATE],
        "PATCH": [perms.SLOT_EDIT],
        "DELETE": [perms.SLOT_DELETE],
    }
    scopes = {
        "GET": [scopes.SCHEDULE_READ],
        "POST": [scopes.SLOT_WRITE],
        "PATCH": [scopes.SLOT_WRITE],
        "DELETE": [scopes.SLOT_WRITE],
    }
    queryset = models.Slot.objects.all()
    serializer_class = serializers.SlotSerializer
    ordering_fields = ("start",)
    filterset_class = filters.SlotFilter
    search_fields = ("status", "schedule__description")

    _data_partition_field = "branch_id"

    def create_slots_for_day(
        self,
        schedule_id: UUID | str,
        day: str,
        request: AuthenticatedRequest,
    ) -> None:
        """Create slots for a particular schedule on a particular day."""
        parsed_day = parse_date(day)
        start_of_day = normalize_to_start_of_day(parsed_day)

        if models.Slot.objects.filter(
            start__date=parsed_day, status=SLOT_STATUS.BUSY_UNAVAILABLE
        ).exists():
            return

        schedule = models.Schedule.objects.get(pk=schedule_id)
        slots = []
        today_timings = schedule.timings.filter(day_of_week=str(parsed_day.weekday()))
        for timing in today_timings:
            slots_exist = schedule.schedule_slots.filter(
                start__iso_week_day=int(timing.day_of_week) + 1,
                start__date=day,
                start__time__gte=timing.start,
                end__time__lte=timing.end,
                status=SLOT_STATUS.FREE,
            ).exists()
            if slots_exist:
                continue

            timing_start = start_of_day + timedelta(
                hours=timing.start.hour, minutes=timing.start.minute
            )
            timing_end = start_of_day + timedelta(
                hours=timing.end.hour, minutes=timing.end.minute
            )
            running = timing_start
            while running < timing_end:
                slot_end = running + timedelta(minutes=schedule.slot_duration)
                slots.append(
                    models.Slot(
                        status=SLOT_STATUS.FREE,
                        start=running,
                        end=slot_end,
                        schedule=schedule,
                        organisation=request.user.organisation,
                        cluster_id=schedule.cluster_id,
                        branch_id=schedule.branch_id,
                        department_id=schedule.department_id,
                        workstation_id=schedule.workstation_id,
                        created_by=request.user.guid,
                        updated_by=request.user.guid,
                    )
                )
                running = slot_end
        models.Slot.objects.bulk_create(slots)

    def list(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """List available slots.

        This is NOT a pure GET as it creates slots when the `start`
        & `schedule_id` filters are provided and no slots are available
        for that particular day.
        """
        day = request.GET.get("start", None)
        schedules_filter = request.GET.get("schedule_id", None)
        if day and schedules_filter:
            schedule_ids = schedules_filter.split(",")
            for schedule_id in schedule_ids:
                self.create_slots_for_day(schedule_id, day, request)

        return super().list(request, *args, **kwargs)


class AppointmentView(CacheableBaseView):
    """Appointments viewset."""

    permissions = {
        "GET": [perms.APPOINTMENT_VIEW],
        "POST": [perms.APPOINTMENT_CREATE],
        "PATCH": [perms.APPOINTMENT_EDIT],
        "DELETE": [perms.APPOINTMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.APPOINTMENT_READ],
        "POST": [scopes.APPOINTMENT_WRITE],
        "PATCH": [scopes.APPOINTMENT_WRITE],
        "DELETE": [scopes.APPOINTMENT_WRITE],
    }

    queryset = models.Appointment.objects.all().prefetch_related(
        "patient__person__person_contacts"
    )
    _select_related = [
        "patient",
        "patient__person",
        "slot__schedule",
    ]
    _prefetch_related = [
        "patient__person__person_ids",
    ]
    serializer_class = serializers.AppointmentSerializer

    ordering_fields = (
        "start",
        "appointment_status__display",
    )
    filterset_class = filters.AppointmentFilter
    search_fields = (
        "appointment_status",
        "reason",
        "patient__person__first_name",
        "patient__person__last_name",
        "patient__person__other_names",
    )

    _data_partition_field = "branch_id"
