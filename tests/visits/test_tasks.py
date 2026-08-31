"""Test visits tasks."""
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import partial
from unittest.mock import MagicMock, call, patch

import pytest
import pytz
from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from model_bakery import baker
from nio import AsyncClient

from sil_advantage.common.models import Person, PersonContact
from sil_advantage.common.utilities.cube import CubeJS
from sil_advantage.notifications.models import Group, GroupMember
from sil_advantage.notifications.sms.models import SenderID
from sil_advantage.patients.models import Patient
from sil_advantage.settings.models import OrganisationSetting
from sil_advantage.visits.models import Visit
from sil_advantage.visits.tasks import (
    celery_app,
    complete_visit,
    dispatch_daily_reports,
    send_daily_report_for_org,
    setup_periodic_tasks,
)
from sil_advantage.visits.utils import (
    send_post_visit_survey_sms,
    send_visit_summary_sms,
)
from tests.common.test_common_views import LoggedInMixin
from tests.common.utility import (
    AsyncMagicMock,
    PicklableMagicMock,
    QuintusReponse,
)

MOCK_ROOT = "sil_advantage.visits.tasks."
MOCK_UTILS_ROOT = "sil_advantage.visits.utils."


@override_settings(
    QUINTUS_BACKEND_URL="https://analytics.example.com",
    MATRIX_HOME_SERVER="https://matrix.example.com",
    MATRIX_BOT_UID="@asdf:example.com",
    MATRIX_BOT_PASSWORD="A3df!",
    MATRIX_SECRET="a-secret",
)
@pytest.mark.usefixtures("default_promotional_sender", "default_transactional_sender")
class VisitTasksTestCase(LoggedInMixin):
    """Test visits Tasks."""

    @patch.object(AsyncClient, "join", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "room_create", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "room_invite", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "login", new_callable=AsyncMagicMock)
    @patch(
        "sil_advantage.notifications.matrix.requests",
        new_callable=PicklableMagicMock,
    )
    def setUp(
        self,
        mock_matrix_requests,
        mock_matrix_login,
        mock_create_matrix_room,
        mock_matrix_invite,
        mock_matrix_join,
    ):
        """Set up test environment."""
        super().setUp()

        matrix_uid = "@2bdf4e17-cb39-4626-a29d-a80040d67857:slade360edi.com"
        mock_matrix_requests.post.return_value.json.return_value = {
            "user_id": matrix_uid,
            "access_token": "my-access-token",
            "home_server": "slade360edi.com",
            "device_id": "GVROMSUCDE",
            "well_known": {
                "m.homeserver": {
                    "base_url": "https://matrix.slade360.uat.slade360edi.com/"
                }
            },
            "_cache_key": "2d0340b3bfedb72dfcb845e8d32b31b7",
        }
        mock_create_matrix_room.transport_response.json.return_value = {
            "room_id": "!asdfasdf:example.com",
        }

        self.org = self.global_organisation
        self.org.organisation_name = "Demo Health Services Nyeri"
        self.org.save()

        self.group = baker.make(
            Group,
            role="DAILY_DIGEST",
            organisation=self.org,
        )
        baker.make(
            GroupMember,
            group=self.group,
            person=self.global_person,
            organisation=self.org,
        )
        member = baker.make(
            GroupMember,
            group=self.group,
            organisation=self.org,
        )
        baker.make(
            PersonContact,
            person=member.person,
            contact_type="email",
            contact="stephen@example.com",
        )

        self.person = baker.make(
            Person,
            first_name="Stephen",
            last_name="Mwangi",
            organisation=self.org,
        )
        self.person2 = baker.make(
            Person,
            first_name="Sarah",
            last_name="Njuguna",
            organisation=self.org,
        )
        self.phone_number = baker.make(
            PersonContact,
            person=self.person,
            contact_type="phone_number",
            contact="+254790360360",
        )
        self.patient = baker.make(
            Patient,
            person=self.person,
            organisation=self.org,
        )
        self.patient2 = baker.make(
            Patient,
            person=self.person2,
            organisation=self.org,
        )
        self.visit2 = baker.make(
            Visit,
            status="FINISHED",
            patient=self.patient2,
            appointment=None,
            created_by=self.user.id,
            updated_by=self.user.pk,
        )
        self.visit = baker.make(
            Visit,
            status="FINISHED",
            patient=self.patient,
            appointment=None,
            created_by=self.user.id,
            updated_by=self.user.pk,
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
        )
        self.default_promotional_sender = SenderID.objects.filter(
            name="Slade360Adv"
        ).latest("created")
        self.default_transactional_sender = SenderID.objects.filter(
            name="BeWellApp"
        ).latest("created")

    def test_registering_visits_tasks(self):
        """Test registering tasks with Celery."""
        setup_periodic_tasks()
        assert "sil_advantage.visits.tasks.dispatch_daily_reports" in celery_app.tasks

    @patch(MOCK_ROOT + "send_daily_report_for_org")
    def test_dispatching_reporting_tasks(self, mock_send_daily_report):
        """Test dispatching reporting tasks."""
        dispatch_daily_reports()
        mock_send_daily_report.apply_async.assert_called_once_with(
            queue="advantage_tasks",
            priority=1,
            args=(50,),
        )

    @patch(MOCK_ROOT + "get_wallet_balances")
    @patch(MOCK_ROOT + "django_timezone")
    @patch.object(AsyncClient, "room_send", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "upload", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "login", new_callable=AsyncMagicMock)
    @patch(MOCK_ROOT + "uuid")
    @patch(MOCK_ROOT + "send_email")
    @patch.object(CubeJS, "get_access_token")
    @patch.object(CubeJS, "api_call")
    def test_sending_email_report(
        self,
        mock_cube_api_call,
        mock_cube_login,
        mock_send_email,
        mock_uuid,
        mock_matrix_login,
        mock_matrix_upload,
        mock_matrix_send_to_room,
        mock_now,
        mock_get_wallet_balances,
    ):
        """Test sending daily report email."""
        mock_uuid.uuid4.return_value = "b5030b13-a5c5-4303-86c8-e444ad2d6ebf"
        upload_resp = MagicMock()
        upload_resp.content_uri = "mxc://localhost/haunting"
        mock_matrix_upload.return_value = upload_resp, None
        mock_now.now.return_value = datetime(2022, 9, 11)
        mock_get_wallet_balances.return_value = {
            "bulk_sms_account": {
                "type": "bulk_sms_account",
                "balance": "5000",
            }
        }

        def mocked_cube_query(url, mocked_result=0, *args, **kwargs):
            """Mock queries to Cube."""
            payload = kwargs["payload"]

            # mirror everything back with 0s :/
            fields = payload.get("measures", []) + payload.get("dimensions", [])
            if len(fields) == 1:
                data = [dict.fromkeys(fields, mocked_result)]
            else:
                data = []

            return QuintusReponse(data={"data": data})

        mock_cube_api_call.side_effect = partial(mocked_cube_query, mocked_result=1)

        send_daily_report_for_org(50)
        mock_send_email.assert_called_once_with(
            subject="SladeAdvantage Daily Digest",
            to=["mail@mail.com", "stephen@example.com"],
            bcc=[
                "advantage@savannahinformatics.com",
                "gtm@savannahinformatics.com",
                "clientsuccess@savannahinformatics.com",
            ],
            html_temp="daily_report_email.mjml",
            plain_text="daily_report_email.mjml",
            context_obj={
                "patients_new_count": 0,
                "visits_started_count": 0,
                "total_discount_amount": 0,
                "total_waived_amount": 0,
                "payment_amounts_by_method": [
                    {"amount": 0, "paymentMethod": 0},
                ],
                "payments_total_amount_collected": 0,
                "uploaded_documents": 0,
                "uploaded_documents_yesterday": 0,
                "approved_documents": 0,
                "pending_documents": 0,
                "rejected_documents": 0,
                "total_patient_documents": 0,
                "total_invoice_count": 0,
                "total_invoiced_amount": 0,
                "service_points_analysis": [
                    {
                        "service_point": "Consultation",
                        "count": 0,
                        "totalPrice": 0,
                    },
                    {
                        "service_point": "Lab",
                        "count": 0,
                        "totalPrice": 0,
                    },
                    {
                        "service_point": "Imaging",
                        "count": 0,
                        "totalPrice": 0,
                    },
                    {
                        "service_point": "Pharmacy",
                        "count": 0,
                        "totalPrice": 0,
                    },
                    {
                        "service_point": "Billing",
                        "count": 0,
                        "totalPrice": 0,
                    },
                    {
                        "service_point": "Procedure",
                        "count": 0,
                        "totalPrice": 0,
                    },
                    {
                        "service_point": "Optical",
                        "count": 0,
                        "totalPrice": 0,
                    },
                    {
                        "service_point": "Breast Cancer Screening",
                        "count": 0,
                        "totalPrice": 0,
                    },
                    {
                        "service_point": "Cervical Cancer Screening",
                        "count": 0,
                        "totalPrice": 0,
                    },
                ],
                "total_outstanding_amount": 0,
                "patients_revisits_count": 0,
                "uploaded_percentage": 0,
                "sms_wallet_balance": Decimal("5000"),
                "sms_wallet_balance_low": False,
                "greeting": "Howdy",
                "api_host": "http://localhost:8000",
                "yesterday": date(2022, 9, 10),
                "currency_prefix": "KSh",
            },
            org_name="Demo Health Services Nyeri",
            headers={
                "X-Entity-Ref-ID": "b5030b13-a5c5-4303-86c8-e444ad2d6ebf",
            },
        )
        mock_matrix_send_to_room.assert_called_once()

    @patch(MOCK_ROOT + "LOGGER")
    def test_sending_email_report_no_message_group(self, mock_logger):
        """Test sending an email report with no message group."""
        send_daily_report_for_org(125)
        mock_logger.warning.assert_called_once_with(
            "Org 125 has no recipients for the daily stats email report."
        )

    @patch("sil_advantage.visits.utils.send_custom_sms")
    @patch("sil_advantage.common.api_clients.shlink.get_shlink_client")
    def test_completing_a_finished_visit(
        self, mock_get_shlink_client, mock_send_custom_sms
    ):
        """Test completing a FINISHED visit."""
        mock_client = MagicMock()
        mock_client.shorten_url.return_value = {
            "shortUrl": "https://e.slade360.com/fmpSv"
        }
        mock_get_shlink_client.return_value = mock_client

        visit = baker.make(
            Visit,
            status="IN_PROGRESS",
            patient=self.patient,
            organisation=self.org,
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
        )
        local_tz = pytz.timezone(settings.TIME_ZONE)
        local_start = visit.start.astimezone(local_tz)
        date_str = local_start.strftime("%a %b-%d")
        OrganisationSetting.set_org_setting(
            self.org,
            "visits:post_visit_surveys_enabled",
            True,
        )

        person = visit.patient.person
        priority = settings.CELERY_TASK_LOW_PRIORITY

        random.seed(42)
        visit.status = "FINISHED"
        visit.save()
        link = "https://e.slade360.com/fmpSv"

        expected_args_send_custom_sms = (
            "POST_VISIT_SURVEY",
            "+254790360360",
            person.organisation,
            visit.branch_id,
            person,
            priority,
        )
        kwargs = {
            "date": date_str,
            "link": link,
            "department_id": visit.department_id,
            "workstation_id": visit.workstation_id,
        }
        mock_send_custom_sms.return_value = {
            "intention": expected_args_send_custom_sms[0],
            "message": "Test message",
            "recipients": [expected_args_send_custom_sms[1]],
            "owner": expected_args_send_custom_sms[3],
            "priority": expected_args_send_custom_sms[4],
            "department_id": kwargs.get("department_id"),
            "workstation_id": kwargs.get("workstation_id"),
        }
        send_post_visit_survey_sms(visit)

        mock_send_custom_sms.assert_called_with(
            *expected_args_send_custom_sms, **kwargs
        )

    @override_settings(
        ADVANTAGE_FRONTEND_URL="http://localhost:4200",
        CELERY_TASK_LOW_PRIORITY=1,
    )
    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    @patch("sil_advantage.visits.utils.generate_token")
    @patch("sil_advantage.common.api_clients.shlink.get_shlink_client")
    def test_send_survey_after_visit_completion_using_promo_sender_setting(
        self, mock_get_shlink_client, mock_visit_token, mock_send_sms
    ):
        """Test completing a FINISHED visit."""
        mock_client = MagicMock()
        mock_client.shorten_url.return_value = {
            "shortUrl": "https://e.slade360.com/fmpSv"
        }
        mock_get_shlink_client.return_value = mock_client
        mock_visit_token.return_value = "JZZOQYwp"

        visit = baker.make(
            Visit,
            status="IN_PROGRESS",
            patient=self.patient,
            organisation=self.org,
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
        )
        OrganisationSetting.set_org_setting(
            self.org,
            "visits:post_visit_surveys_enabled",
            True,
        )

        random.seed(42)
        visit.status = "FINISHED"
        visit.save()

        visit_date = visit.start.strftime("%a %b-%d")
        assert mock_send_sms.call_count == 2

        mock_send_sms.assert_has_calls(
            [
                call(
                    queue="advantage_tasks",
                    priority=1,
                    args=(
                        "POST_VISIT_SURVEY",
                        "Hi Stephen, following your visit "
                        "at Demo Health Services Nyeri on "
                        f"{visit_date}, kindly assist us understand "
                        "how we can serve you better "
                        "by following https://e.slade360.com/fmpSv "
                        "to fill in our survey",
                        ["+254790360360"],
                        self.org.slade_code,
                        visit.branch_id,
                        None,
                    ),
                    kwargs={"sender_id": self.default_promotional_sender.id},
                ),
                call(
                    queue="advantage_tasks",
                    priority=1,
                    args=(
                        "VISIT_SUMMARY",
                        "Dear Stephen, Thank you for choosing our services "
                        "at Demo Health Services Nyeri on "
                        f"{visit_date}. You can "
                        "access your receipt here "
                        "https://e.slade360.com/fmpSv "
                        "In case of any concerns please call us on +254799999999.",
                        ["+254790360360"],
                        self.org.slade_code,
                        visit.branch_id,
                        None,
                    ),
                    kwargs={"sender_id": self.default_transactional_sender.id},
                ),
            ]
        )

    @override_settings(
        ADVANTAGE_FRONTEND_URL="http://localhost:4200",
        CELERY_TASK_LOW_PRIORITY=1,
    )
    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    @patch("sil_advantage.visits.utils.generate_token")
    @patch("sil_advantage.common.api_clients.shlink.get_shlink_client")
    def test_send_survey_after_visit_completion_using_custom_promo_sender_setting(
        self, mock_get_shlink_client, mock_visit_token, mock_send_sms
    ):
        """Test completing a FINISHED visit."""
        mock_client = MagicMock()
        mock_client.shorten_url.return_value = {
            "shortUrl": "https://e.slade360.com/fmpSv"
        }
        mock_get_shlink_client.return_value = mock_client

        mock_visit_token.return_value = "JZZOQYwp"

        custom_promo_sender = baker.make(
            SenderID,
            name="OregonInfo",
            sender_type="PROMOTION",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            active=True,
        )
        OrganisationSetting.set_branch_setting(
            self.org,
            self.visit.branch_id,
            "billing:promotional_sender_id",
            "OregonInfo",
        )

        visit = baker.make(
            Visit,
            status="IN_PROGRESS",
            patient=self.patient,
            organisation=self.org,
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
        )

        random.seed(42)
        visit.status = "FINISHED"
        visit.save()
        visit_date = visit.start.strftime("%a %b-%d")

        assert mock_send_sms.call_count == 2

        mock_send_sms.assert_has_calls(
            [
                call(
                    queue="advantage_tasks",
                    priority=1,
                    args=(
                        "POST_VISIT_SURVEY",
                        "Hi Stephen, following your visit "
                        "at Demo Health Services Nyeri on "
                        f"{visit_date}, kindly assist us understand "
                        "how we can serve you better "
                        "by following https://e.slade360.com/fmpSv "
                        "to fill in our survey",
                        ["+254790360360"],
                        self.org.slade_code,
                        visit.branch_id,
                        None,
                    ),
                    kwargs={"sender_id": custom_promo_sender.id},
                ),
                call(
                    queue="advantage_tasks",
                    priority=1,
                    args=(
                        "VISIT_SUMMARY",
                        "Dear Stephen, Thank you for choosing our services "
                        "at Demo Health Services Nyeri on "
                        f"{visit_date}. You can "
                        "access your receipt here "
                        "https://e.slade360.com/fmpSv "
                        "In case of any concerns please call us on +254799999999.",
                        ["+254790360360"],
                        self.org.slade_code,
                        visit.branch_id,
                        None,
                    ),
                    kwargs={"sender_id": self.default_transactional_sender.id},
                ),
            ]
        )

    @patch(MOCK_ROOT + "LOGGER")
    def test_completing_an_in_progress_visit(self, mock_logger):
        """Test completing a visit that's in progress."""
        visit = baker.make(
            Visit,
            status="IN_PROGRESS",
            patient=self.patient,
            organisation=self.org,
        )
        OrganisationSetting.set_org_setting(
            self.org,
            "visits:post_visit_surveys_enabled",
            True,
        )

        complete_visit(visit.id)

        mock_logger.warning.assert_called_once_with(
            f"Visit {visit.id} not in FINISHED state."
        )

    @patch(MOCK_ROOT + "send_visit_summary_sms")
    @patch(MOCK_ROOT + "LOGGER")
    def test_completing_a_visit_post_visit_survey_disabled(
        self,
        mock_logger,
        mock_visit_sms,
    ):
        """Test completing a visit with post visit surveys disabled."""
        visit = baker.make(
            Visit,
            status="FINISHED",
            patient=self.patient,
            organisation=self.org,
        )
        OrganisationSetting.set_org_setting(
            self.org,
            "visits:post_visit_surveys_enabled",
            False,
        )

        complete_visit(visit.id)

        mock_logger.warning.assert_called_once_with(
            "Organisation with slade code 50 not enabled to send post visit surveys."
        )

    @patch("sil_advantage.visits.utils.send_custom_sms")
    @patch("sil_advantage.visits.utils.generate_token")
    @patch("sil_advantage.common.api_clients.shlink.get_shlink_client")
    def test_send_visit_summary_sms(
        self, mock_get_shlink_client, mock_generate_token, mock_send_custom_sms
    ):
        """Test sending visit summary sms."""
        mock_client = MagicMock()
        mock_client.shorten_url.return_value = {
            "shortUrl": "http://localhost:4200/summary?t=JZZOQYwp"
        }
        mock_get_shlink_client.return_value = mock_client

        mock_generate_token.return_value = "JZZOQYwp"

        send_visit_summary_sms(self.visit)

        mock_generate_token.assert_called_once_with(8)
        mock_send_custom_sms.assert_called_once_with(
            "VISIT_SUMMARY",
            self.person.phone_number,
            self.visit.organisation,
            self.visit.branch_id,
            self.person,
            settings.CELERY_TASK_LOW_PRIORITY,
            date=self.visit.start.strftime("%a %b-%d"),
            link=settings.ADVANTAGE_FRONTEND_URL + "/summary?t=JZZOQYwp",
            org_phone_number=self.visit.organisation.phone_number,
            department_id=self.visit.department_id,
            workstation_id=self.visit.workstation_id,
        )

    @patch("sil_advantage.visits.utils.send_custom_sms")
    @patch("sil_advantage.visits.utils.generate_token")
    def test_send_visit_summary_sms_no_phone_number(
        self, mock_generate_token, mock_send_custom_sms
    ):
        """Test sending visit summary sms without phonenumber."""
        visit = self.visit2

        send_visit_summary_sms(visit)

        mock_generate_token.assert_not_called()
        mock_send_custom_sms.assert_not_called()
