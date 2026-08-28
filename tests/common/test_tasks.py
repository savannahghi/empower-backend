"""Test common tasks."""

from datetime import timedelta
from unittest.mock import MagicMock, call, patch

import pytest
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from model_bakery import baker
from requests import ConnectionError
from sil_monitoring import Monitor

from sil_advantage.billing.models import (
    BillableItem,
    ClinicalOrder,
    Invoice,
    Refund,
    RefundLine,
)
from sil_advantage.common.models.common_models import Person, PersonContact
from sil_advantage.common.models.organisation_models import Organisation
from sil_advantage.common.tasks import (
    BaseTaskWithRetry,
    retry_failed_to_sync_objects,
    send_practitioner_daily_digest_message,
    setup_periodic_tasks,
)
from sil_advantage.config import celery_app
from sil_advantage.notifications.sms.models import SenderID
from sil_advantage.patients.models import Patient
from sil_advantage.practitioners.models import Practitioner
from sil_advantage.scheduling import SLOT_STATUS
from sil_advantage.scheduling.models import Appointment, Schedule, Slot
from sil_advantage.visits.models import Queue, Visit
from tests.common.test_common_views import LoggedInMixin

MOCK_ROOT = "sil_advantage.common.tasks."


class TestTaskMonitor(TestCase):
    """Test task monitor."""

    def test_registering_common_tasks(self):
        """Test registering tasks with Celery."""
        setup_periodic_tasks()
        assert (
            "sil_advantage.common.tasks.sync_org_updates_with_remote"
            in celery_app.tasks
        )

    @patch.object(Monitor, "timer")
    @patch.object(Monitor, "increment")
    def test_task_succeeded(
        self,
        mock_monitor_incr,
        mock_monitor_timer,
    ):
        """Test task succeeded."""

        @celery_app.task(base=BaseTaskWithRetry)
        def task_a():
            """Sample task."""
            ...

        task_a.delay()

        mock_monitor_incr.assert_called_once_with(
            "celery_tasks_succeeded",
            tags={"name": "task_a"},
        )
        mock_monitor_timer.assert_called_once_with(
            "celery_tasks_duration",
            tags={"name": "task_a"},
        )

    @patch.object(Monitor, "timer")
    @patch.object(Monitor, "increment")
    def test_task_failure(self, mock_monitor_incr, mock_monitor_timer):
        """Test task failure."""

        @celery_app.task(base=BaseTaskWithRetry)
        def task_b():
            """Sample task."""
            raise ConnectionError()

        task_b.delay()

        tags = {"name": "task_b", "exception": "ConnectionError"}
        mock_monitor_incr.assert_has_calls(
            [
                call("celery_tasks_retried", tags=tags),
                call("celery_tasks_retried", tags=tags),
                call("celery_tasks_retried", tags=tags),
                call("celery_tasks_retried", tags=tags),
                call("celery_tasks_failed", tags=tags),
            ]
        )
        assert mock_monitor_timer.call_count == 5


@pytest.mark.usefixtures("organisation", "default_transactional_sender")
class TestPractitionerTasks(TestCase):
    """Test task monitor."""

    def setUp(self) -> None:
        """Setup test environment."""
        self.org = Organisation.objects.get(organisation_name="Demo Hospital")
        self.patient = baker.make(
            Patient, person__first_name="Mary", person__last_name="Jane"
        )
        self.default_transactional_sender = SenderID.objects.filter(
            name="BeWellApp"
        ).latest("created")
        person = baker.make(
            Person,
            organisation=self.org,
            title="Dr",
            first_name="John",
            last_name="Doe",
        )
        baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254712345678",
        )
        self.practitioner = baker.make(
            Practitioner,
            person=person,
            qualification="RADIOLOGY",
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
        )
        super().setUp()

    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    @patch("sil_advantage.scheduling.models." + "timezone")
    @patch(MOCK_ROOT + "timezone")
    @patch(MOCK_ROOT + "shlink_shorten_url")
    def test_send_practitioner_daily_digest_message(
        self, mock_shlink_shorten_url, mock_timezone, mock_slot_timezone, mock_send_sms
    ):
        """Test sending practitioner daily digest notification."""
        dt = timezone.datetime(2023, 11, 9).replace(tzinfo=timezone.utc)
        mock_timezone.now.return_value = dt
        mock_slot_timezone.now.return_value = dt

        mock_shlink_shorten_url.return_value = "https://e.slade360.com/nvTz1"

        schedule = baker.make(
            Schedule,
            slot_duration=30,
            organisation=self.org,
            practitioner=self.practitioner,
        )

        day = parse_datetime("2023-11-09 00:05+00:00") + timedelta(hours=10)
        slot_start = day + timedelta(minutes=30)
        slot_end = slot_start + timedelta(minutes=30)
        slot = baker.make(
            Slot,
            start=slot_start,
            end=slot_end,
            schedule=schedule,
            status=SLOT_STATUS.FREE,
            organisation=self.org,
        )
        branch_id = self.practitioner.branch_id
        kwargs = {
            "reason": "some reason",
            "description": "needs spectacles",
            "start": slot_start,
            "end": slot_end,
            "slot": slot,
            "organisation": self.org,
            "appointment_status": "BOOKED",
            "patient": self.patient,
        }
        baker.make(Appointment, **kwargs)
        # ignore appointment creation mock call
        mock_send_sms.reset_mock()
        send_practitioner_daily_digest_message()
        mock_send_sms.assert_called_once_with(
            queue="advantage_tasks",
            priority=1,
            args=(
                "PRACTITIONER_DAILY_DIGEST",
                "Hi Dr John, you have 1 appointment(s) today at Demo Hospital. "
                "To view more, click https://e.slade360.com/nvTz1",
                ["+254712345678"],
                self.org.slade_code,
                branch_id,
                None,
            ),
            kwargs={"sender_id": self.default_transactional_sender.id},
        )

    @patch("sil_advantage.scheduling.models." + "timezone")
    @patch(MOCK_ROOT + "timezone")
    @patch(MOCK_ROOT + "LOGGER")
    def test_send_practitioner_daily_digest_message_no_phone_number(
        self, mock_logger, mock_timezone, mock_slot_timezone
    ):
        """Test sending daily digest notification without phone number."""
        dt = timezone.datetime(2023, 11, 9).replace(tzinfo=timezone.utc)
        mock_timezone.now.return_value = dt
        mock_slot_timezone.now.return_value = dt

        contact = PersonContact.objects.get(person=self.practitioner.person)
        contact.delete()

        schedule = baker.make(
            Schedule,
            slot_duration=30,
            organisation=self.org,
            practitioner=self.practitioner,
        )

        day = parse_datetime("2023-11-09 00:05+00:00") + timedelta(hours=10)
        slot_start = day + timedelta(minutes=30)
        slot_end = slot_start + timedelta(minutes=30)
        slot = baker.make(
            Slot,
            start=slot_start,
            end=slot_end,
            schedule=schedule,
            status=SLOT_STATUS.FREE,
            organisation=self.org,
        )
        kwargs = {
            "reason": "some reason",
            "description": "needs spectacles",
            "start": slot_start,
            "end": slot_end,
            "slot": slot,
            "organisation": self.org,
            "appointment_status": "BOOKED",
            "patient": self.patient,
        }
        baker.make(Appointment, **kwargs)
        send_practitioner_daily_digest_message()
        mock_logger.warning.assert_called_once_with(
            "No phone number configured for this practitioner"
        )

    @patch("sil_advantage.scheduling.models." + "timezone")
    @patch(MOCK_ROOT + "timezone")
    @patch(MOCK_ROOT + "LOGGER")
    def test_send_practitioner_daily_digest_message_no_appointments(
        self, mock_logger, mock_timezone, mock_slot_timezone
    ):
        """Test sending daily digest notification without appointments."""
        dt = timezone.datetime(2023, 11, 9).replace(tzinfo=timezone.utc)
        mock_timezone.now.return_value = dt
        mock_slot_timezone.now.return_value = dt

        schedule = baker.make(
            Schedule,
            slot_duration=30,
            organisation=self.org,
            practitioner=self.practitioner,
        )

        day = parse_datetime("2023-11-09 00:05+00:00") + timedelta(hours=10)
        slot_start = day + timedelta(minutes=30)
        slot_end = slot_start + timedelta(minutes=30)
        baker.make(
            Slot,
            start=slot_start,
            end=slot_end,
            schedule=schedule,
            status=SLOT_STATUS.FREE,
            organisation=self.org,
        )
        send_practitioner_daily_digest_message()
        mock_logger.warning.assert_called_once_with(
            "No appointments scheduled for this practitioner"
        )


class TestSyncToRemoteRetryTask(LoggedInMixin):
    """Test sync to remote retry task."""

    def setUp(self) -> None:
        """Setup test environment."""
        super().setUp()
        self.person = baker.make(
            Person,
            first_name="John",
            last_name="Doe",
            deceased=False,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.queue = baker.make(Queue)

    @override_settings(SYNC_WITH_ERP=True)
    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_retry_failed_to_sync_objects_succesfully(self, mock_create_erp_login):
        """Test retry of failed to sync remote objects."""
        mock_erp = MagicMock()
        mock_erp.customers.create.return_value = {}
        mock_create_erp_login.return_value = mock_erp

        data = {
            "person": self.person,
            "organisation": self.person.organisation,
            "created_by": self.user.id,
            "updated_by": self.user.id,
        }
        patient = Patient.objects.create(**data)
        patient.refresh_from_db()
        assert patient.customer_id is None
        mock_erp.reset_mock(return_value=True)
        mock_erp.currencies.list.return_value = {
            "results": [
                {
                    "id": "eec240d6-f3a6-4012-a842-852d02a385d2",
                    "iso_code": "KES",
                }
            ]
        }
        mock_erp.customers.create.return_value = {
            "id": "b9f17e45-cd51-4041-ae94-9b5c9f5c99c2",
        }
        retry_failed_to_sync_objects()
        mock_erp.customers.create.assert_called_once_with(
            {
                "partner_name": "John Doe",
                "is_customer": True,
                "organisation": "ebef581c-494b-4772-9e49-0b0755c44e61",
                "customer_type": "PATIENT",
                "country": "KEN",
                "created_by": "1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
                "updated_by": "1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
                "currency": "eec240d6-f3a6-4012-a842-852d02a385d2",
            }
        )
        patient.refresh_from_db()
        assert str(patient.customer_id) == "b9f17e45-cd51-4041-ae94-9b5c9f5c99c2"

    @override_settings(SYNC_WITH_ERP=False)
    def test_should_not_retry_failed_to_sync_objects(self):
        """Test retry of failed to sync remote objects."""
        data = {
            "person": self.person,
            "organisation": self.person.organisation,
            "created_by": self.user.id,
            "updated_by": self.user.id,
        }
        patient = Patient.objects.create(**data)
        patient.refresh_from_db()
        assert patient.customer_id is None

        retry_failed_to_sync_objects()
        patient.refresh_from_db()
        assert patient.customer_id is None

    @override_settings(SYNC_WITH_ERP=True)
    @patch(MOCK_ROOT + "LOGGER")
    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_retry_failed_to_sync_objects_with_failures(
        self, mock_create_erp_login, mock_logger
    ):
        """Test successful syncing retry with failed record."""
        mock_erp = MagicMock()
        mock_erp.currencies.list.return_value = {
            "results": [
                {
                    "id": "eec240d6-f3a6-4012-a842-852d02a385d2",
                    "iso_code": "KES",
                }
            ]
        }
        mock_erp.customers.create.side_effect = [
            {
                "id": "b9f17e45-cd51-4041-ae94-9b5c9f5c99c2",
            },
            {},
        ]
        mock_erp.sales_invoices.create.return_value = {}
        mock_create_erp_login.return_value = mock_erp

        data = {
            "person": self.person,
            "organisation": self.person.organisation,
            "created_by": self.user.id,
            "updated_by": self.user.id,
        }
        patient = Patient.objects.create(**data)

        person_two = baker.make(
            Person,
            first_name="Mary",
            last_name="Jane",
            deceased=False,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        data = {
            "person": person_two,
            "organisation": self.person.organisation,
            "created_by": self.user.id,
            "updated_by": self.user.id,
        }
        patient_two = Patient.objects.create(**data)

        patient.refresh_from_db()
        patient_two.refresh_from_db()
        assert str(patient.customer_id) == "b9f17e45-cd51-4041-ae94-9b5c9f5c99c2"
        assert patient_two.customer_id is None

        baker.make(
            Visit,
            patient=patient,
            current_queue=self.queue,
            status="ARRIVED",
            created_by=self.user.id,
            updated_by=self.user.id,
            department_id="6db73406-4d24-445b-9896-564eb1a480b4",
        )

        order = ClinicalOrder.objects.latest("created")
        Invoice.objects.update(
            workflow_state="PROCESSED",
        )

        invoice = Invoice.objects.latest("created")
        billable_item_1, billable_item_2 = baker.make(
            BillableItem,
            product_id="a1a8a97f-1a6a-4c7d-a64f-007f3ef75072",
            pricelist_product_id="fdd90a71-3ebe-444c-9a52-9aa79300a07b",
            clinical_order=order,
            invoice=invoice,
            quantity=2,
            price=2_000,
            _quantity=2,
        )
        refund = baker.make(
            Refund,
            invoice=invoice,
            department_id=invoice.department_id,
            reason="Jamii waiver applied hence warrants a refund processed.",
            kra_reason_code=("10"),
        )
        refund_line = baker.make(
            RefundLine,
            refund=refund,
            invoice_line=billable_item_1,
            quantity=2,
        )
        refund_line2 = baker.make(
            RefundLine,
            refund=refund,
            invoice_line=billable_item_2,
            quantity=2,
        )

        invoice.refresh_from_db()
        billable_item_1.refresh_from_db()
        billable_item_2.refresh_from_db()
        assert invoice.sales_invoice_id is None
        assert billable_item_1.sales_invoice_line_id is None
        assert billable_item_2.sales_invoice_line_id is None
        assert refund.sales_credit_note_id is None
        assert refund_line.sales_credit_note_line_id is None
        assert refund_line2.sales_credit_note_line_id is None

        mock_erp.reset_mock(return_value=True)
        mock_erp.currencies.list.return_value = {}
        mock_erp.sales_invoices.create.return_value = {
            "id": "5a41d7bb-fcc9-4cf8-ac65-4dfd1a882ad8",
            "workflow_state": "SUBMITTED",
        }
        mock_erp.sales_order_lines.create.return_value = {
            "id": "583cbe42-d987-4a05-b6b1-c2339f4551c0",
        }
        mock_erp.sales_invoice_lines.create.side_effect = [
            {
                "id": "1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
                "new_price": "2000",
                "tax_code_description": "D-non VAT",
            },
            {
                "id": "454718ff-45ff-423e-b652-f6b138f62bff",
            },
        ]
        retry_failed_to_sync_objects()

        patient_two.refresh_from_db()
        assert patient_two.customer_id is None

        invoice.refresh_from_db()
        assert invoice.sales_invoice_id is None

        billable_item_1.refresh_from_db()
        assert (
            str(billable_item_1.sales_invoice_line_id)
            == "1d7494c0-2d13-4140-aa54-2ef7d14e48cd"
        )
