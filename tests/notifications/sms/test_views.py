"""Test SMS Views."""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import UUID

import pytest
import time_machine
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker
from rest_framework import status

from sil_advantage.common.models.common_models import Person, UserProfile
from sil_advantage.common.models.organisation_models import Organisation
from sil_advantage.notifications.sms.models import SMS, SenderID, SMSLogReport
from sil_advantage.permissions import perms
from sil_advantage.settings.models import OrganisationSetting
from sil_advantage.sil_auth.models import SILUser
from tests.common.test_common_views import (
    LoggedInMixin,
    get_project_permissions,
)

MOCK_ROOT = "sil_advantage.notifications.sms.views."


@pytest.mark.usefixtures("default_transactional_sender")
@override_settings(
    SIL_COMMS_API_CONFIG={
        "api_host": "api.sandbox.comms.slade360.co.ke",
        "api_scheme": "https",
        "oauth_client_id": "1oauth-client-id",
        "oauth_client_secret": "2oauth-client-secret",
        "user_email": "silcomms.testing@savannahinformatics.com",
        "user_password": "avErYsecurepa33w0rd",
        "token_url": "https://authserver.comms.slade360.co.ke/oauth2/token/",
    }
)
class SMSViewsetTestCase(LoggedInMixin):
    """Test SMS viewset."""

    def setUp(self):
        """Update test environment."""
        super().setUp()
        self.default_transactional_sender = SenderID.objects.filter(
            name="BeWellApp"
        ).latest("created")
        OrganisationSetting.set_branch_setting(
            organisation=self.global_organisation,
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
            setting_name="billing:transactional_sender_id",
            value="BeWellApp",
        )
        self.workstation_data = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }
        self.headers = {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    @patch(MOCK_ROOT + "utils.can_send_sms")
    @patch(MOCK_ROOT + "tasks.send_sms.apply_async")
    def test_send_dm_sms_from_ui(self, mock_send_sms, mock_can_send_sms):
        """Test sending a DM SMS from the UI."""
        mock_can_send_sms.return_value = (True, None, 1, 0, None)

        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"
        headers = {"HTTP_X_BRANCH": branch_id}

        url = reverse("send-sms")
        payload = {
            "intention": "DIRECT_MESSAGE",
            "recipients": ["+254790360360"],
            "message": "Hi, your test results are ready.",
        }

        self.client.post(url, payload, **headers).json()

        mock_send_sms.assert_called_once_with(
            queue="advantage_tasks",
            priority=5,
            args=(
                "DIRECT_MESSAGE",
                "Hi, your test results are ready. ~ Demo Hospital",
                ["+254790360360"],
                self.global_organisation.slade_code,
                "abf685c2-9cc5-4d17-aa81-9944a0f590fa",
                None,
            ),
            kwargs={"sender_id": self.default_transactional_sender.id},
        )

    @patch(MOCK_ROOT + "utils.can_send_sms")
    @patch(MOCK_ROOT + "tasks.send_sms.apply_async")
    def test_send_dm_sms_from_ui_no_balance(
        self,
        mock_send_sms,
        mock_can_send_sms,
    ):
        """Test sending a DM SMS from the UI without a wallet balance."""
        mock_can_send_sms.return_value = (False, "No balance", 1, 0, None)

        url = reverse("send-sms")
        payload = {
            "intention": "DIRECT_MESSAGE",
            "recipients": ["+254790360360"],
            "message": "Hi, your test results are ready 💀.",
        }

        response = self.client.post(url, payload)
        assert response.status_code == 400
        assert response.json() == ["No balance"]

        mock_send_sms.assert_not_called()

    @patch(MOCK_ROOT + "tasks.process_delivery_report.apply_async")
    def test_sms_callback(self, mock_process_delivery_report):
        """Test receiving an SMS callback from SIL Comms."""
        sender = baker.make(
            SenderID,
            name="Slade360",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            organisation=self.global_organisation,
            sender_type="TRANSACTION",
            active=True,
        )

        baker.make(
            SMS,
            organisation=self.global_organisation,
            sender=sender,
            message="Hi there",
            recipients=["+254722345678"],
            intention="BROADCAST",
            sil_comms_sms_id=UUID("616d9996-4dc9-4909-a30d-e8a965a4dc7a"),
        )
        baker.make(
            SMS,
            organisation=self.global_organisation,
            sender=sender,
            message="Hello there",
            recipients=["+254746104918"],
            intention="BROADCAST",
        )

        url = reverse("sms-list")
        data = self.client.get(f"{url}?search=Hello").json()
        assert data["count"] == 1

        data = self.client.get(f"{url}?search=+254746104918").json()
        assert data["count"] == 1

        data = self.client.get(f"{url}?search=+254722345678").json()
        assert data["count"] == 1

        data = self.client.get(f"{url}?search=BeWell").json()
        assert data["count"] == 0

        url = reverse("sms-callback")
        payload = {
            "status": "success",
            "message": "SUCCESS",
            "type": "DELIVERY_REPORT",
            "data": {
                "guid": "616d9996-4dc9-4909-a30d-e8a965a4dc7a",
                "body": "New phone, who dis?",
                "msisdn": "+254722345678",
                "sms_type": "BULK",
                "gateway": "SAFARICOM",
                "carrier": "639/01",
                "subscription": None,
                "direction": "OUTBOUND",
                "state": "DELIVERED",
                "created": "2022-09-16T11:46:05.049824+03:00>",
                "updated": "2022-09-16T11:46:05.153662+03:00",
            },
        }

        self.client.post(url, payload)

        mock_process_delivery_report.assert_called_once_with(
            queue="advantage_tasks",
            priority=5,
            args=(payload,),
        )

    @patch(MOCK_ROOT + "tasks.process_interactive_shortcode.apply_async")
    def test_interactive_shortcode_callback(self, mock_process_interactive_shortcode):
        """Test the processing of an interactive shortcode SMS response."""
        self.sender = baker.make(
            SenderID,
            name="232435",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
        )

        self.admin_user = baker.make(
            SILUser,
            email="network.admin@slade360.co.ke",
            password="pass123",
            is_active=True,
            is_staff=True,
            guid=uuid.uuid4(),
            matrix_user_id="@user:slade360edi.com",
        )

        if not self.user.is_active or not self.user.active:
            self.user.is_active = True
            self.user.active = True
            self.user.save()

        url = reverse("interactive-shortcode-callback")
        payload = {
            "type": "INTERACTIVE_SHORTCODE_RESPONSE",
            "data": {
                "Msisdn": "+254722345678",
                "Shortcode": "232435",
                "Response": "Test Message",
            },
        }
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        mock_process_interactive_shortcode.assert_called_once_with(
            args=(
                {
                    "Msisdn": "+254722345678",
                    "Shortcode": "232435",
                    "Response": "Test Message",
                },
            ),  # noqa
            queue="advantage_tasks",
            priority=5,
        )

    @patch(MOCK_ROOT + "tasks.generate_sms_log_report.apply_async")
    def test_generate_sms_log_report(self, mock_generate_sms_log_report):
        """Test generating sms log report."""
        url = reverse("sms-generate-sms-log-report")
        payload = {
            "delivery_type": "OUTBOUND",
            "date_from": "2024-07-30",
            "date_to": "2024-08-30",
        }

        self.client.post(url, payload)
        sms_report_obj = SMSLogReport.objects.filter().latest("created")

        mock_generate_sms_log_report.assert_called_once_with(
            queue="advantage_tasks",
            priority=5,
            args=(payload, sms_report_obj.id),
        )


class SenderIDViewsetTestCase(LoggedInMixin):
    """Test SenderID ViewSet."""

    def setUp(self):
        """Set up the test environment."""
        super().setUp()

        baker.make(
            SenderID,
            name="Slade360",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            organisation=self.global_organisation,
            sender_type="TRANSACTION",
            active=True,
        )
        baker.make(
            SenderID,
            name="Slade360Promo",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            organisation=self.global_organisation,
            sender_type="PROMOTION",
            active=True,
        )

        # setup external Sender IDs
        self.test_org = baker.make(Organisation, organisation_name="AccessAfya")
        baker.make(
            SenderID,
            name="AccessAfya",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            organisation=self.test_org,
            sender_type="TRANSACTION",
            active=True,
        )

    @override_settings(SIL_COMMS_TRANSACTIONAL_SENDER_ID="Slade360")
    @override_settings(SIL_COMMS_PROMOTIONAL_SENDER_ID="Slade360Promo")
    def test_list_sender_ids(self):
        """Test listing an organisation's sender ids."""
        url = reverse("senderid-list")
        response = self.client.get(url)

        assert response.status_code == 200
        assert response.data["count"] == 2

        # test sender search
        url = reverse("senderid-list")

        response = self.client.get(
            url + "?search=Slade360",
        ).json()
        assert response["count"] == 2

        response = self.client.get(
            url + "?search=Slade360Promo",
        ).json()
        assert response["count"] == 1

        response = self.client.get(
            url + "?search=Oregon",
        ).json()
        assert response["count"] == 0

    def test_promotional_disabled_sender_ids(self):
        """Test a disabled sender ID."""
        url = reverse("senderid-list")

        # Local time: 09:00
        with time_machine.travel(
            datetime(
                year=2024,
                month=10,
                day=7,
                hour=6,
            )
        ):
            response = self.client.get(url)

            assert response.status_code == 200
            assert response.data["count"] == 2

            results = response.data["results"]

            assert results[0]["name"] == "Slade360Promo"
            assert results[0]["sender_type"] == "PROMOTION"

            assert results[0]["disabled"]["status"] is False
            assert results[0]["disabled"]["reason"] is None

        # Local time: 05:00
        with time_machine.travel(
            datetime(
                year=2024,
                month=10,
                day=7,
                hour=2,
            )
        ):
            response = self.client.get(url)

            assert response.status_code == 200
            assert response.data["count"] == 2

            results = response.data["results"]

            assert results[0]["name"] == "Slade360Promo"
            assert results[0]["sender_type"] == "PROMOTION"

            assert results[0]["disabled"]["status"] is True
            assert (
                results[0]["disabled"]["reason"]
                == "This option is only available from 8:00 AM to 6:00 PM."
            )

    @override_settings(SIL_COMMS_TRANSACTIONAL_SENDER_ID="Slade360")
    @override_settings(SIL_COMMS_PROMOTIONAL_SENDER_ID="Slade360Promo")
    def test_list_default_sender_ids(self):
        """Test listing default sender ids."""
        url = reverse("senderid-list")
        org = baker.make(Organisation, organisation_name="Oregon")
        assert SenderID.objects.filter(organisation=org).count() == 0

        permissions = set(get_project_permissions())
        permissions.remove(perms.CROSS_NETWORK_ADMIN[0])
        permissions.remove(perms.ORGANISATION_ADMIN[0])
        permissions.remove(perms.BRANCH_ADMIN[0])
        permissions.remove(perms.CLUSTER_ADMIN[0])
        permissions = ",".join(permissions)

        user = get_user_model().objects.create_superuser(
            email="john@mail.com",
            password="pass123",
            id="048d488a-34a6-4140-9635-552e98fa3cbf",
            guid="048d488a-34a6-4140-9635-552e98fa3cbf",
            matrix_user_id="@2bdf4e17-cb39-4626-a29d-a80040d67857:slade360edi.com",
            permissions=permissions,
        )
        global_person = baker.make(
            Person,
            branch_id="1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
            organisation=org,
            first_name="John",
            last_name="Doe",
        )
        baker.make(
            UserProfile,
            user=user,
            person=global_person,
            organisation=org,
        )

        self.client.logout()
        assert self.client.login(username="john@mail.com", password="pass123") is True
        response = self.client.get(url)
        assert response.status_code == 200

        data = response.json()
        assert data["count"] == 2


class SMSLogReportViewsetTestCase(LoggedInMixin):
    """Test SMSLogReport ViewSet."""

    def setUp(self):
        """Set up the test environment."""
        super().setUp()

        self.workstation_data = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }
        self.headers = {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    def test_list_sms_log_report_detail(self):
        """Test SMSLogReport detail view."""
        sms_log_report = baker.make(
            SMSLogReport,
            organisation=self.global_organisation,
            process_state="COMPLETE",
            **self.workstation_data,
        )

        url = reverse("smslogreport-detail", kwargs={"pk": sms_log_report.id})
        response = self.client.get(url, **self.headers).json()
        assert response["id"] == str(sms_log_report.id)
