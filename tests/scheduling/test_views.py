"""Test scheduling views."""
from datetime import time, timedelta
from itertools import cycle
from unittest.mock import Mock

import pytz
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from model_bakery import baker, recipe
from rest_framework.exceptions import ErrorDetail

from sil_advantage.patients.models import Patient
from sil_advantage.scheduling import (
    APPOINTMENT_STATUS,
    PRACTITIONER_TYPES,
    SLOT_STATUS,
    models,
)
from sil_advantage.scheduling.views import SlotView
from sil_advantage.sil_auth.models import SILUser
from tests.common.test_common_views import LoggedInMixin


class ScheduleTestCase(LoggedInMixin):
    """Test the schedule viewset."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.workstation_data = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    def extra_headers(self):
        """Workstation headers."""
        return {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    def test_create_schedule(self):
        """Test creating a schedule."""
        payload = {
            "description": "Dr. Jane Doe",
            "specialty": "GENERAL PRACTITIONER",
            "slot_duration": 30,
            "availability": {
                "0": [{"start": "08:00", "end": "17:00"}],
                "1": [{"start": "14:00", "end": "17:00"}],
                "2": [{"start": "08:00", "end": "17:00"}],
                "3": [
                    {"start": "08:00", "end": "12:00"},
                    {"start": "14:00", "end": "17:00"},
                ],
                "5": [],
                "6": [{"start": "10:00", "end": "12:00"}],
            },
            **self.workstation_data,
        }
        url = reverse("schedules-list")
        resp = self.client.post(url, payload)
        assert resp.status_code == 201, resp.data

        schedule_id = resp.data["id"]
        schedule = models.Schedule.objects.get(pk=schedule_id)
        assert schedule.description == "Dr. Jane Doe"
        assert schedule.specialty == "GENERAL PRACTITIONER"
        assert schedule.slot_duration == 30
        assert schedule.availability == {
            "0": [{"start": time(8, 0), "end": time(17, 0)}],
            "1": [{"start": time(14, 0), "end": time(17, 0)}],
            "2": [{"start": time(8, 0), "end": time(17, 0)}],
            "3": [
                {"start": time(8, 0), "end": time(12, 0)},
                {"start": time(14, 0), "end": time(17, 0)},
            ],
            "6": [{"start": time(10, 0), "end": time(12, 0)}],
        }
        # slots are created on demand
        assert schedule.schedule_slots.count() == 0

    def test_create_checkin_schedule(self):
        """Test creating a check-in schedule."""
        payload = {
            "description": "Check-in Queue",
            "actor": "FACILITY",
            "specialty": "OTHER",
            "slot_duration": 1439,
            "availability": {
                "0": [{"start": "00:00", "end": "23:59"}],
                "1": [{"start": "00:00", "end": "23:59"}],
                "2": [{"start": "00:00", "end": "23:59"}],
                "3": [{"start": "00:00", "end": "23:59"}],
                "4": [{"start": "00:00", "end": "23:59"}],
                "5": [{"start": "00:00", "end": "23:59"}],
                "6": [{"start": "00:00", "end": "23:59"}],
            },
            **self.workstation_data,
        }
        url = reverse("schedules-list")
        resp = self.client.post(url, payload)
        assert resp.status_code == 201, resp.data

        schedule_id = resp.data["id"]
        schedule = models.Schedule.objects.get(pk=schedule_id)
        assert schedule.actor == "FACILITY"

    def test_validate_timing_start_greater_than_end(self):
        """Test validation of schedule timings."""
        payload = {
            "description": "Dr. Jane Doe",
            "specialty": "GENERAL PRACTITIONER",
            "slot_duration": 30,
            "availability": {
                "0": [{"start": "08:00", "end": "17:00"}],
                "1": [{"start": "14:00", "end": "17:00"}],
                "2": [{"start": "08:00", "end": "17:00"}],
                "3": [
                    {"start": "12:00", "end": "08:00"},
                    {"start": "14:00", "end": "17:00"},
                ],
                "5": [],
                "6": [{"start": "10:00", "end": "12:00"}],
            },
            **self.workstation_data,
        }
        url = reverse("schedules-list")
        resp = self.client.post(url, payload)
        assert resp.status_code == 400, resp.data

        assert resp.data == {"end": ["The timing end must be greater than its start."]}

    def test_validate_availability_overlap(self):
        """Test validation of availability overlap."""
        payload = {
            "description": "Dr. Jane Doe",
            "specialty": "GENERAL PRACTITIONER",
            "slot_duration": 30,
            "availability": {
                "0": [{"start": "08:00", "end": "17:00"}],
                "1": [{"start": "14:00", "end": "17:00"}],
                "2": [{"start": "08:00", "end": "17:00"}],
                "3": [
                    {"start": "08:00", "end": "14:01"},
                    {"start": "14:00", "end": "17:00"},
                ],
                "5": [],
                "6": [{"start": "10:00", "end": "12:00"}],
            },
            **self.workstation_data,
        }
        url = reverse("schedules-list")
        resp = self.client.post(url, payload)
        assert resp.status_code == 400, resp.data

        assert resp.data == ["Availability on Thursday overlaps."]

    def test_patch_schedule(self):
        """Test updated schedules."""
        assert models.Slot.objects.count() == 0

        payload = {
            "description": "Checkup6",
            "specialty": "GENERAL PRACTITIONER",
            "slot_duration": 30,
            "availability": {
                "0": [{"start": "08:00", "end": "17:00"}],
                "1": [{"start": "14:00", "end": "17:00"}],
                "2": [{"start": "08:00", "end": "17:00"}],
                "3": [
                    {"start": "08:00", "end": "12:00"},
                    {"start": "14:00", "end": "17:00"},
                ],
                "5": [],
                "6": [{"start": "10:00", "end": "12:00"}],
            },
            **self.workstation_data,
        }
        url = reverse("schedules-list")
        resp = self.client.post(url, payload)
        assert resp.status_code == 201, resp.data

        # create slots
        schedule_id = resp.data["id"]
        slots_url = reverse("slots-list")
        self.client.get(slots_url + f"?schedule_id={schedule_id}&start=2022-12-05")
        assert models.Slot.objects.count() == 18

        # book a slot
        slot = models.Slot.objects.first()
        models.Slot.model_validators = []
        slot.status = SLOT_STATUS.BUSY
        slot.save()

        # update availability
        updated_availability = {
            "0": [
                {"start": "10:00", "end": "12:00"},
                {"start": "14:00", "end": "17:00"},
            ],
            "2": [{"start": "08:00", "end": "17:00"}],
            "3": [],
            "5": [
                {"start": "09:00", "end": "13:00"},
                {"start": "15:00", "end": "17:30"},
            ],
        }
        update_with = {
            "description": "Prescription",
            "slot_duration": 15,
            "availability": updated_availability,
        }
        url = reverse("schedules-detail", kwargs={"pk": schedule_id})
        response = self.client.patch(url, update_with)
        assert response.status_code == 200
        assert response.data["description"] == update_with["description"]
        schedule = models.Schedule.objects.get(pk=schedule_id)
        schedule.refresh_from_db()
        assert schedule.availability == {
            "0": [
                {"start": time(10, 0), "end": time(12, 0)},
                {"start": time(14, 0), "end": time(17, 0)},
            ],
            "2": [{"start": time(8, 0), "end": time(17, 0)}],
            "5": [
                {"start": time(9, 0), "end": time(13, 0)},
                {"start": time(15, 0), "end": time(17, 30)},
            ],
        }
        assert models.Slot.objects.count() == 1

        # create slots with new availability
        schedule_id = resp.data["id"]
        slots_url = reverse("slots-list")
        self.client.get(slots_url + f"?schedule_id={schedule_id}&start=2022-12-05")
        assert models.Slot.objects.count() == 21

    def test_patch_schedule_availability_validations(self):
        """Test that availability validations run after an update."""
        payload = {
            "description": "Checkup6",
            "specialty": "GENERAL PRACTITIONER",
            "slot_duration": 30,
            "availability": {
                "0": [{"start": "08:00", "end": "17:00"}],
                "1": [{"start": "14:00", "end": "17:00"}],
                "2": [{"start": "08:00", "end": "17:00"}],
                "3": [
                    {"start": "08:00", "end": "12:00"},
                    {"start": "14:00", "end": "17:00"},
                ],
                "5": [],
                "6": [{"start": "10:00", "end": "12:00"}],
            },
            **self.workstation_data,
        }
        url = reverse("schedules-list")
        resp = self.client.post(url, payload)
        assert resp.status_code == 201, resp.data

        # create slots
        schedule_id = resp.data["id"]
        slots_url = reverse("slots-list")
        self.client.get(slots_url + f"?schedule_id={schedule_id}&start=2022-12-05")
        assert models.Slot.objects.count() == 18

        # book a slot
        slot = models.Slot.objects.first()
        models.Slot.model_validators = []
        slot.status = SLOT_STATUS.BUSY
        slot.save()

        # update availability
        updated_availability = {
            "0": [
                {"start": "10:00", "end": "15:30"},
                {"start": "14:00", "end": "17:00"},
            ],
            "2": [{"start": "08:00", "end": "17:00"}],
            "3": [],
            "5": [
                {"start": "09:00", "end": "13:00"},
                {"start": "15:00", "end": "17:30"},
            ],
        }
        update_with = {
            "description": "Prescription",
            "slot_duration": 15,
            "availability": updated_availability,
        }
        url = reverse("schedules-detail", kwargs={"pk": schedule_id})
        response = self.client.patch(url, update_with)
        assert response.status_code == 400
        assert response.data == [
            ErrorDetail(string="Availability on Monday overlaps.", code="invalid")
        ]

    def test_put_schedule(self):
        """Test if an appointment can be added to existing slot."""
        payload = {
            "description": "Checkup6",
            "specialty": "GENERAL PRACTITIONER",
            "slot_duration": 30,
            "availability": {
                "0": [{"start": "08:00", "end": "17:00"}],
                "1": [{"start": "14:00", "end": "17:00"}],
                "2": [{"start": "08:00", "end": "17:00"}],
                "3": [
                    {"start": "08:00", "end": "12:00"},
                    {"start": "14:00", "end": "17:00"},
                ],
                "5": [],
                "6": [{"start": "10:00", "end": "12:00"}],
            },
            **self.workstation_data,
        }
        url = reverse("schedules-list")
        resp = self.client.post(url, payload)
        assert resp.status_code == 201, resp.data

        schedule_id = resp.data["id"]
        data = {
            "organisation": self.user.organisation.pk,
            "description": "Checkup",
            "specialty": "ORTHODONTICS",
            "slot_duration": 30,
        }
        url = reverse("schedules-detail", kwargs={"pk": schedule_id})
        response = self.client.put(url, data)
        assert response.status_code == 200, response.data
        assert response.data["description"] == data["description"]
        assert response.data["specialty"] == data["specialty"]

    def test_cancel_all_days_appointments(self):
        """Test cancelling appointments on a specific day."""
        schedule = baker.make(
            models.Schedule,
            slot_duration=30,
            organisation=self.global_organisation,
            **self.workstation_data,
        )
        day = parse_datetime("2042-02-27 00:00+03:00") + timedelta(hours=10)
        slot_starts = [
            day + timedelta(minutes=30),
            day + timedelta(minutes=120),
            day + timedelta(days=2, minutes=60),
        ]
        slot_ends = list(
            map(
                lambda slot_start: slot_start + timedelta(minutes=30),
                slot_starts,
            )
        )
        slots_recipe = recipe.Recipe(
            models.Slot,
            start=cycle(slot_starts),
            end=cycle(slot_ends),
            schedule=schedule,
            status=SLOT_STATUS.FREE,
            organisation=self.global_organisation,
            **self.workstation_data,
        )
        slots = slots_recipe.make(_quantity=3)
        appts_recipe = recipe.Recipe(
            models.Appointment,
            start=cycle(slot_starts),
            end=cycle(slot_ends),
            slot=cycle(slots),
            appointment_status=APPOINTMENT_STATUS.BOOKED,
            organisation=self.global_organisation,
            patient__organisation=self.global_organisation,
            **self.workstation_data,
        )
        appt1, appt2, appt3 = appts_recipe.make(_quantity=3)

        url = reverse(
            "schedules-cancel-day-appts",
            kwargs={"pk": schedule.pk},
        )

        # required param not provided
        response = self.client.get(url)
        assert response.status_code == 400
        assert response.data == [
            ErrorDetail(string="Please provide a date.", code="invalid")
        ]

        # date provided
        response = self.client.get(url + "?date=2042-02-27")
        assert response.status_code == 200
        assert response.data == "OK"
        appt1.refresh_from_db()
        assert appt1.appointment_status == "CANCELLED"
        appt2.refresh_from_db()
        assert appt2.appointment_status == "CANCELLED"
        appt3.refresh_from_db()
        assert appt3.appointment_status == "BOOKED"

    def test_search_specialties(self):
        """Test the listing and search of specialties."""
        url = reverse("schedules-specialties")
        # list without search
        response = self.client.get(url)
        assert response.status_code == 200
        assert len(response.data) == len(PRACTITIONER_TYPES)

        # list with search
        response = self.client.get(url + "?search=MEDICINE")
        assert response.data == [
            "FAMILY MEDICINE",
            "INTERNAL MEDICINE",
            "EMERGENCY MEDICINE",
            "PALLIATIVE MEDICINE",
            "FUNCTIONAL MEDICINE",
            "OCCUPATIONAL MEDICINE",
            "DERMATOLOGY  INTERNAL MEDICINE",
            "INTERNAL MEDICINE  ONCOLOGY/RADIOTHERAPY",
        ]

        # check that search is case insensitive
        response = self.client.get(url + "?search=surgery")
        assert response.data == [
            "NEUROSURGERY",
            "GENERAL SURGERY",
            "PLASTIC SURGERY",
            "PAEDIATRIC SURGERY",
            "ORTHOPAEDIC SURGERY",
            "GENERAL SURGERY  ORTHOPAEDICS",
            "ORAL AND MAXILLOFACIAL SURGERY",
            "ORTHOPAEDICS AND TRAUMA SURGERY",
            "GENERAL SURGERY  PLASTIC SURGERY",
            "EAR  NOSE AND THROAT (ENT SURGERY)",
            "GENERAL SURGERY  PAEDIATRIC SURGERY",
        ]

        # search with multiple words
        response = self.client.get(url + "?search=internal med")
        assert response.data == [
            "DERMATOLOGY  INTERNAL MEDICINE",
            "INTERNAL MEDICINE  ONCOLOGY/RADIOTHERAPY",
            "INTERNAL MEDICINE",
        ]

        # bad search param
        response = self.client.get(url + "?tafuta=surgery")
        assert len(response.data) == len(PRACTITIONER_TYPES)

    def test_block_calendar_slots_for_a_day(self):
        """Test blocking slots on a specific day."""
        schedule = baker.make(
            models.Schedule,
            slot_duration=30,
            organisation=self.global_organisation,
        )
        day = timezone.now() + timezone.timedelta(days=1)
        slot_starts = [
            day + timezone.timedelta(minutes=30),
            day + timezone.timedelta(minutes=120),
            day + timezone.timedelta(days=2, minutes=60),
        ]
        slot_ends = list(
            map(
                lambda slot_start: slot_start + timezone.timedelta(minutes=30),
                slot_starts,
            )
        )
        slots_recipe = recipe.Recipe(
            models.Slot,
            start=cycle(slot_starts),
            end=cycle(slot_ends),
            schedule=schedule,
            status=SLOT_STATUS.BUSY_UNAVAILABLE,
            organisation=self.global_organisation,
        )
        slots = slots_recipe.make(_quantity=3)

        url = reverse(
            "schedules-block-slots",
            kwargs={"pk": schedule.pk},
        )

        response = self.client.get(url)
        assert response.status_code == 400
        assert response.data == [
            ErrorDetail(string="Please provide a date.", code="invalid")
        ]

        response_date = (timezone.now() + timezone.timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        response = self.client.get(url + f"?date={response_date}")
        assert response.status_code == 200
        assert response.data == {"detail": "Slots for the date have been blocked."}
        for slot in slots:
            slot.refresh_from_db()
            assert slot.status == SLOT_STATUS.BUSY_UNAVAILABLE

    def test_block_calendar_for_specified_date_ranges_within_a_week(self):
        """Test blocking slots on a range of days within a week."""
        schedule = baker.make(
            models.Schedule,
            slot_duration=30,
            organisation=self.global_organisation,
        )
        start_day = timezone.now() + timezone.timedelta(days=1)
        end_day = start_day + timezone.timedelta(days=2)

        url = reverse(
            "schedules-block-slots",
            kwargs={"pk": schedule.pk},
        )

        response_start_date = start_day.strftime("%Y-%m-%d")
        response_end_date = end_day.strftime("%Y-%m-%d")
        response = self.client.get(
            url + f"?date={response_start_date}&end_date={response_end_date}"
        )
        assert response.status_code == 200
        assert response.data == {"detail": "Slots for the date have been blocked."}

    def test_block_calendar_for_the_blocked_time_range_within_a_day(self):
        """Test blocking slots within a specific time range on a specific day."""
        schedule = baker.make(
            models.Schedule,
            slot_duration=30,
            organisation=self.global_organisation,
        )
        day = timezone.now() + timezone.timedelta(days=1)

        url = reverse(
            "schedules-block-slots",
            kwargs={"pk": schedule.pk},
        )

        response_date = day.strftime("%Y-%m-%d")
        response_start_time = "09:00:00"
        response_end_time = "12:00:00"
        response = self.client.get(
            url + f"?date={response_date}&start_time={response_start_time}"
            f"&end_time={response_end_time}"
        )
        assert response.status_code == 200
        assert response.data == {"detail": "Slots for the date have been blocked."}

    def test_unblock_calendar_slots_for_time_range_for_day(self):
        """Test unblocking slots within a specific time range on a specific day."""
        schedule = baker.make(
            models.Schedule,
            slot_duration=30,
            organisation=self.global_organisation,
        )
        day = timezone.now() + timezone.timedelta(days=1)

        url = reverse(
            "schedules-unblock-slots",
            kwargs={"pk": schedule.pk},
        )
        response_date = day.strftime("%Y-%m-%d")
        response_start_time = "09:00:00"
        response_end_time = "12:00:00"
        response = self.client.get(
            url + f"?date={response_date}&start_time={response_start_time}"
            f"&end_time={response_end_time}"
        )
        assert response.status_code == 200
        assert response.data == {"detail": "Slots for the date have been unblocked."}

    def test_unblock_calendar_slots_for_a_specific_day(self):
        """Test unblocking slots on a specific day ."""
        schedule = baker.make(
            models.Schedule,
            slot_duration=30,
            organisation=self.global_organisation,
        )
        day = timezone.now() + timezone.timedelta(days=1)
        slot_starts = [
            day + timezone.timedelta(minutes=30),
            day + timezone.timedelta(minutes=120),
        ]
        slot_ends = list(
            map(
                lambda slot_start: slot_start + timezone.timedelta(minutes=30),
                slot_starts,
            )
        )
        slots_recipe = recipe.Recipe(
            models.Slot,
            start=cycle(slot_starts),
            end=cycle(slot_ends),
            schedule=schedule,
            status=SLOT_STATUS.BUSY_UNAVAILABLE,
            organisation=self.global_organisation,
        )
        slots = slots_recipe.make(_quantity=2)

        url = reverse(
            "schedules-unblock-slots",
            kwargs={"pk": schedule.pk},
        )
        response = self.client.get(url)
        assert response.status_code == 400
        assert str(response.data[0]) == "Please provide a date."

        response_date = day.strftime("%Y-%m-%d")
        response = self.client.get(url + f"?date={response_date}")
        assert response.status_code == 200
        assert response.data == {"detail": "Slots for the date have been unblocked."}
        for slot in slots:
            slot.refresh_from_db()
            assert slot.status == SLOT_STATUS.FREE

    def test_block_current_date_against_previous_date(self):
        """Test blocking slots with invalid dates."""
        schedule = baker.make(
            models.Schedule,
            slot_duration=30,
            organisation=self.global_organisation,
        )

        url = reverse(
            "schedules-block-slots",
            kwargs={"pk": schedule.pk},
        )

        start_date = (timezone.now() + timezone.timedelta(days=2)).strftime("%Y-%m-%d")
        end_date = (timezone.now() + timezone.timedelta(days=1)).strftime("%Y-%m-%d")

        response = self.client.get(url + f"?date={start_date}&end_date={end_date}")
        assert response.status_code == 400
        assert response.data == [
            ErrorDetail(
                string="End date cannot be earlier than start date.", code="invalid"
            )
        ]


class SlotTestCase(LoggedInMixin):
    """Test slots viewset."""

    def setUp(self):
        """Test the display of the slot data."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.url = reverse("slots-list")
        self.workstation_data = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }
        super().setUp()

    def extra_headers(self):
        """Workstation headers."""
        return {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    def test_create_slot(self):
        """Assert that a slot can be created."""
        schedule = "Checkup1"
        org = self.global_organisation
        sch = baker.make(
            models.Schedule,
            slot_duration=30,
            description=schedule,
            organisation=org,
            **self.workstation_data,
        )

        status = SLOT_STATUS.BUSY
        start = timezone.now() + timezone.timedelta(600)
        end = start + timezone.timedelta(200)
        parse_date = end.strftime("%Y-%m-%dT%H:%M:%S.%f+03:00")
        data = {
            "status": status,
            "start": start,
            "end": parse_date,
            "schedule": sch.pk,
            "organisation": org.pk,
        }

        response = self.client.post(self.url, data)
        assert response.status_code == 201
        assert response.data["end"] == data["end"]

    def test_retrieve_slot(self):
        """Validate a slot can be retrieved using the url."""
        schedule = "Checkup1"
        org = self.global_organisation
        sch = baker.make(
            models.Schedule,
            slot_duration=30,
            description=schedule,
            organisation=org,
            **self.workstation_data,
        )

        status = SLOT_STATUS.BUSY
        start = timezone.now() + timezone.timedelta(500)
        end = start + timezone.timedelta(500)
        local_tz = pytz.timezone(settings.TIME_ZONE)
        parse_date = end.astimezone(local_tz).strftime("%Y-%m-%dT%H:%M:%S.%f+03:00")
        data = {
            "status": status,
            "start": start,
            "end": parse_date,
            "schedule": sch.pk,
            "organisation": org.pk,
        }
        self.client.post(self.url, data)
        response = self.client.get(self.url)
        start = start.astimezone(local_tz).strftime("%Y-%m-%dT%H:%M:%S.%f+03:00")
        assert response.data["count"] == 1
        slot = [s["start"] for s in response.data["results"]]
        assert start in slot

    def test_patch_slot(self):
        """Test a slot exists and can be created."""
        start_update = timezone.now() + timezone.timedelta(600)
        schedule = "Checkup1"
        org = self.global_organisation
        sch = baker.make(
            models.Schedule,
            slot_duration=30,
            description=schedule,
            organisation=org,
            **self.workstation_data,
        )

        status = SLOT_STATUS.BUSY
        start = timezone.now() + timezone.timedelta(500)
        end = start + timezone.timedelta(500)
        parse_date = end.strftime("%Y-%m-%dT%H:%M:%S.%f+03:00")
        data = {
            "status": status,
            "start": start,
            "end": parse_date,
            "schedule": sch.pk,
            "organisation": org.pk,
        }
        self.client.post(self.url, data)
        pk = models.Slot.objects.first().id
        parse_start = start_update.strftime("%Y-%m-%dT%H:%M:%S.%f+03:00")
        update_with = {"start": parse_start}
        url = reverse("slots-detail", kwargs={"pk": pk})
        response = self.client.patch(url, update_with)
        assert response.data["start"] == update_with["start"]

    def test_put_slot(self):
        """Test that a slot can be saved with its details."""
        org = self.global_organisation
        sch = baker.make(
            models.Schedule,
            slot_duration=30,
            organisation=org,
            **self.workstation_data,
        )
        status = SLOT_STATUS.BUSY

        start = timezone.now() + timezone.timedelta(500)
        end = start + timezone.timedelta(500)

        edited_start = timezone.now() + timezone.timedelta(510)
        edited_end = start + timezone.timedelta(450)
        ps = baker.make(
            models.Slot,
            status=status,
            start=start,
            end=end,
            schedule=sch,
            organisation=org,
            **self.workstation_data,
        )
        data = {
            "status": status,
            "start": edited_start,
            "end": edited_end,
            "schedule": sch.pk,
            "organisation": org.pk,
        }
        url = reverse("slots-detail", kwargs={"pk": ps.pk})
        response = self.client.put(url, data)
        assert response.status_code == 200
        assert data["status"] in response.data["status"]

    def test_create_slots_on_demand(self):
        """Test creation of slots on demand."""
        # create the schedule & its timings
        payload = {
            "description": "Dr. Jane Doe",
            "specialty": "GENERAL PRACTITIONER",
            "slot_duration": 30,
            "availability": {
                "0": [{"start": "08:00", "end": "17:00"}],
                "1": [{"start": "14:00", "end": "17:00"}],
                "2": [{"start": "08:00", "end": "17:00"}],
                "3": [
                    {"start": "08:00", "end": "12:00"},
                    {"start": "14:00", "end": "17:00"},
                ],
                "5": [],
                "6": [{"start": "10:00", "end": "12:00"}],
            },
            **self.workstation_data,
        }
        url = reverse("schedules-list")
        resp = self.client.post(url, payload)
        assert resp.status_code == 201

        url = reverse("slots-list")
        # normal "listing"
        response = self.client.get(url).json()
        assert response["count"] == 0

        # create on demand
        schedule_id = resp.data["id"]
        response = self.client.get(
            url + f"?schedule_id={schedule_id}&start=2022-12-01"
        ).json()
        assert response["count"] == 14

        # test idempotency
        schedule_id = resp.data["id"]
        response = self.client.get(
            url + f"?schedule_id={schedule_id}&start=2022-12-01"
        ).json()
        assert response["count"] == 14

        # test with day that doesn't have timings
        schedule_id = resp.data["id"]
        response = self.client.get(
            url + f"?schedule_id={schedule_id}&start=2022-12-03"
        ).json()
        assert response["count"] == 0

    def test_create_slots_for_day_with_busy_slots(self):
        """Test that create slots for a day returns when there are unavailable."""
        # Create a schedule
        schedule = baker.make(
            models.Schedule,
            slot_duration=30,
            organisation=self.global_organisation,
            **self.workstation_data,
        )

        # Create a slot with status BUSY_UNAVAILABLE for a future date
        day = timezone.now() + timedelta(days=2)
        start = day + timedelta(hours=2)
        end = start + timedelta(minutes=30)
        baker.make(
            models.Slot,
            start=start,
            end=end,
            schedule=schedule,
            status=SLOT_STATUS.BUSY_UNAVAILABLE,
            organisation=self.global_organisation,
            **self.workstation_data,
        )

        view = SlotView()
        view.create_slots_for_day(schedule.pk, day.date().isoformat(), Mock())

        # Check that no new slots were created for the day
        slots = models.Slot.objects.filter(start__date=day.date())
        assert slots.count() == 1
        assert slots.first().status == SLOT_STATUS.BUSY_UNAVAILABLE


class AppointmentTestCase(LoggedInMixin):
    """Test appointment viewset."""

    def setUp(self):
        """Test the representation of the view."""
        super().setUp()
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")

        self.workstation_data = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

        self.start_slot = timezone.now() + timezone.timedelta(500)
        self.end_slot = self.start_slot + timezone.timedelta(300)

        self.start_date = timezone.now() + timezone.timedelta(510)
        self.end_date = self.start_date + timezone.timedelta(200)

        self.org = self.global_organisation
        self.sch = baker.make(
            models.Schedule,
            organisation=self.org,
            slot_duration=30,
            **self.workstation_data,
        )
        self.slot = baker.make(
            models.Slot,
            start=self.start_slot,
            end=self.end_slot,
            schedule=self.sch,
            organisation=self.org,
            status=SLOT_STATUS.FREE,
            **self.workstation_data,
        )
        self.url = reverse("appointments-list")
        self.patient = baker.make(
            Patient,
            person__first_name="Jane",
            person__last_name="Doe",
            **self.workstation_data,
        )

    def extra_headers(self):
        """Workstation headers."""
        return {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    def test_appointment_create(self):
        """Test if an appointment can be created."""
        patient = baker.make(
            Patient,
            organisation=self.org,
            **self.workstation_data,
        )
        appst = APPOINTMENT_STATUS.BOOKED
        reason = "Reason Mwitu"
        local_tz = pytz.timezone(settings.TIME_ZONE)
        start_date = self.end_slot.astimezone(local_tz).strftime(
            "%Y-%m-%dT%H:%M:%S.%f+03:00"
        )
        end_date = self.end_slot.astimezone(local_tz).strftime(
            "%Y-%m-%dT%H:%M:%S.%f+03:00"
        )
        data = {
            "reason": reason,
            "description": "Dry coughs",
            "slot": self.slot.pk,
            "appointment_status": appst,
            "organisation": self.global_organisation.pk,
            "patient": patient.pk,
            "start": start_date,
            "end": end_date,
            **self.workstation_data,
        }
        response = self.client.post(self.url, data)
        assert response.status_code == 201, response.data
        assert response.data["end"] == end_date

    def test_appointment_retrieve(self):
        """Test if the saved appointment can be retrieved."""
        appointment_status = APPOINTMENT_STATUS.BOOKED
        baker.make(
            models.Appointment,
            start=self.start_date,
            end=self.end_date,
            slot=self.slot,
            appointment_status=appointment_status,
            organisation=self.org,
            patient=self.patient,
            **self.workstation_data,
        )
        response = self.client.get(self.url)
        assert response.data["count"] == 1
        local_tz = pytz.timezone(settings.TIME_ZONE)
        retrieve_end_date = self.end_date.astimezone(local_tz).strftime(
            "%Y-%m-%dT%H:%M:%S.%f+03:00"
        )
        appointments = [a["end"] for a in response.data["results"]]
        assert retrieve_end_date in appointments

    def test_appointment_patch(self):
        """Test updating an appointment."""
        appointment_status = APPOINTMENT_STATUS.BOOKED
        appt = baker.make(
            models.Appointment,
            description="Chest pains",
            start=self.start_date,
            end=self.end_date,
            slot=self.slot,
            appointment_status=appointment_status,
            organisation=self.org,
            patient=self.patient,
            **self.workstation_data,
        )
        update_with = {"description": "Back pains"}
        url = reverse("appointments-detail", kwargs={"pk": appt.pk})
        response = self.client.patch(url, update_with)
        assert response.status_code == 200
        assert response.data["description"] == update_with["description"]

        # test update timeslot
        assert appt.slot == self.slot
        assert appt.slot.status == SLOT_STATUS.BUSY
        new_slot_start = self.start_slot + timedelta(days=1)
        slot2 = baker.make(
            models.Slot,
            start=new_slot_start,
            end=new_slot_start + timezone.timedelta(minutes=15),
            schedule=self.sch,
            **self.workstation_data,
        )
        update_with = {"slot": slot2.pk}
        response = self.client.patch(url, update_with)
        assert response.status_code == 200
        appt.refresh_from_db()
        assert appt.slot == slot2
        assert appt.start == slot2.start
        assert appt.end == slot2.end
        self.slot.refresh_from_db()
        assert self.slot.status == SLOT_STATUS.FREE
        slot2.refresh_from_db()
        assert slot2.status == SLOT_STATUS.BUSY
