"""Test SMS Tasks."""
from datetime import date, timedelta
from unittest.mock import Mock, call, patch
from uuid import UUID, uuid4

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from model_bakery import baker
from sil_edge_connection import ApiConnection

from sil_advantage.common.models.common_models import Person
from sil_advantage.common.models.organisation_models import Organisation
from sil_advantage.notifications.sms.models import (
    SMS,
    ProcessState,
    SenderID,
    SMSLogReport,
)
from sil_advantage.notifications.sms.tasks import (
    generate_sms_log_report,
    process_delivery_report,
    process_interactive_shortcode,
    send_sms,
)
from sil_advantage.segments.models import (
    MessageTemplate,
    Segment,
    SegmentMember,
    SegmentMessageDelivery,
)
from sil_advantage.sil_auth.models import SILUser
from tests.common.test_common_views import global_organisation
from tests.common.utility import PicklableMagicMock

MOCK_ROOT = "sil_advantage.notifications.sms.tasks."


@override_settings(
    SIL_COMMS_PROMOTIONAL_SENDER_ID="BeWellInfo",
    SIL_COMMS_TRANSACTIONAL_SENDER_ID="BeWellApp",
    SIL_COMMS_API_CONFIG={
        "api_host": "api.sandbox.comms.slade360.co.ke",
        "api_scheme": "https",
        "oauth_client_id": "1oauth-client-id",
        "oauth_client_secret": "2oauth-client-secret",
        "user_email": "silcomms.testing@savannahinformatics.com",
        "user_password": "avErYsecurepa33w0rd",
        "token_url": "https://authserver.comms.slade360.co.ke/oauth2/token/",
    },
    SIL_COMMS_BUSINESS_PARTNER_APP_ID="da42d1b8-07e7-4849-b499-f97d292e2533",
)
class SMSTasksTestCase(TestCase):
    """Test SMS Tasks."""

    def setUp(self) -> None:
        """Set up the tests environment."""
        baker.make(SILUser, email="network.admin@slade360.co.ke")

        self.access_afya_sender = baker.make(
            SenderID,
            name="AccessAfyaInfo",
            sender_type="TRANSACTION",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            active=True,
        )
        self.access_afya_promo_sender = baker.make(
            SenderID,
            name="AccessAfyaPromo",
            sender_type="PROMOTION",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            active=True,
        )

        baker.make(
            SenderID,
            name="BeWellApp",
            sender_type="TRANSACTION",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            active=True,
        )
        baker.make(
            SenderID,
            name="BeWellInfo",
            sender_type="PROMOTION",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            active=True,
        )
        self.workstation_data = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }
        super().setUp()
        global_organisation()
        cache.clear()

    @override_settings(ENVIRONMENT="prod")
    @override_settings(SIL_COMMS_TRANSACTIONAL_SENDER_ID="BeWellApp")
    @patch.object(ApiConnection, "call")
    @patch.object(
        ApiConnection,
        "credentials",
        create=True,
        new_callable=PicklableMagicMock,
    )
    @patch.object(ApiConnection, "authenticate")
    def test_send_sms_task_transactional_prod(
        self,
        mock_auth,
        mock_credz,
        mock_api_call,
    ):
        """Test sending an transactional SMS on production."""
        self.client.logout()

        def api_call(url, *args, **kwargs):
            if url == "/api/financial_accounts/accountsbalances/":
                return {
                    "results": [
                        {
                            "_identifiers": "bulk_sms_account",
                            "balance": "2500",
                        }
                    ],
                }
            elif url == "/api/billing/pricing_table_lines/":
                return {
                    "results": [
                        {
                            "organisation": "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
                            "billing_code": "APPOINTMENT_REMINDER_SMS",
                            "rate": "1.0",
                        }
                    ]
                }
            elif url == "/api/common/organisations/":
                return {
                    "results": [
                        {"id": "1107dee0-fa04-4187-a8e8-a4489141d13f"},
                    ],
                }

            return {
                "guid": "583cbe42-d987-4a05-b6b1-c2339f4551c0",
                "sender": "BeWellApp",
                "message": "New phone, who dis? [Test Message]",
                "recipients": ["+254712345678"],
                "state": "QUEUED",
                "sms": ["616d9996-4dc9-4909-a30d-e8a965a4dc7a"],
                "created": "2022-08-04 14:11:17.206377+03:00",
                "updated": "2022-08-04 14:11:17.206377+03:00",
            }

        mock_api_call.side_effect = api_call
        mock_credz.__getitem__.return_value = "435wersgfs45t"
        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"

        send_sms(
            "APPOINTMENT_REMINDER",
            "New phone, who dis?",
            ["+254712345678"],
            50,
            branch_id,
            "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
        )

        mock_api_call.assert_has_calls(
            [
                call(
                    "v1/sms/bulk/",
                    "POST",
                    None,
                    {
                        "sender": "BeWellApp",
                        "message": "New phone, who dis?",
                        "app": "da42d1b8-07e7-4849-b499-f97d292e2533",
                        "recipients": ["+254712345678"],
                        "metadata": {
                            "intention": "APPOINTMENT_REMINDER",
                            "owner": 50,
                            "source": "prod",
                            "service": "SLADE360_ADVANTAGE",
                        },
                    },
                    None,
                    None,
                    False,
                    True,
                )
            ]
        )
        sms = SMS.objects.all()
        assert sms.count() == 1

        assert sms[0].sender.name == "BeWellApp"
        assert sms[0].message == "New phone, who dis?"
        assert sms[0].recipients == ["+254712345678"]
        assert sms[0].intention == "APPOINTMENT_REMINDER"
        assert sms[0].sil_comms_sms_id == UUID("616d9996-4dc9-4909-a30d-e8a965a4dc7a")

    @override_settings(ENVIRONMENT="prod")
    @override_settings(SIL_COMMS_TRANSACTIONAL_SENDER_ID="BeWellApp")
    @patch.object(ApiConnection, "call")
    @patch.object(
        ApiConnection,
        "credentials",
        create=True,
        new_callable=PicklableMagicMock,
    )
    @patch.object(ApiConnection, "authenticate")
    def test_send_sms_task_with_delivery_tracking(
        self,
        mock_auth,
        mock_credz,
        mock_api_call,
    ):
        """Test sending a segment message with delivery tracking."""
        self.client.logout()

        def api_call(url, *args, **kwargs):
            if url == "/api/financial_accounts/accountsbalances/":
                return {
                    "results": [
                        {
                            "_identifiers": "bulk_sms_account",
                            "balance": "2500",
                        }
                    ],
                }
            elif url == "/api/billing/pricing_table_lines/":
                return {
                    "results": [
                        {
                            "organisation": "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
                            "billing_code": "APPOINTMENT_REMINDER_SMS",
                            "rate": "1.0",
                        }
                    ]
                }
            elif url == "/api/common/organisations/":
                return {
                    "results": [
                        {"id": "1107dee0-fa04-4187-a8e8-a4489141d13f"},
                    ],
                }

            return {
                "guid": "583cbe42-d987-4a05-b6b1-c2339f4551c0",
                "sender": "BeWellApp",
                "message": "New phone, who dis? [Test Message]",
                "recipients": ["+254712345678"],
                "state": "QUEUED",
                "sms": ["616d9996-4dc9-4909-a30d-e8a965a4dc7a"],
                "created": "2022-08-04 14:11:17.206377+03:00",
                "updated": "2022-08-04 14:11:17.206377+03:00",
            }

        mock_api_call.side_effect = api_call
        mock_credz.__getitem__.return_value = "435wersgfs45t"

        person = baker.make(Person, organisation=global_organisation())
        segment = baker.make(Segment, organisation=global_organisation())
        message = baker.make(
            MessageTemplate,
            organisation=global_organisation(),
            template="Hello World!",
            message_type="SINGULAR",
        )
        member = baker.make(
            SegmentMember,
            person=person,
            segment=segment,
            organisation=global_organisation(),
        )
        segment_message_delivery_obj = baker.make(
            SegmentMessageDelivery,
            member=member,
            message_template=message,
            organisation=global_organisation(),
        )
        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"

        send_sms(
            "APPOINTMENT_REMINDER",
            "New phone, who dis?",
            ["+254712345678"],
            50,
            branch_id,
            "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
            model_name="segments.segmentmessagedelivery",
            model_obj_pk=segment_message_delivery_obj.id,
        )

        mock_api_call.assert_has_calls(
            [
                call(
                    "v1/sms/bulk/",
                    "POST",
                    None,
                    {
                        "sender": "BeWellApp",
                        "message": "New phone, who dis?",
                        "app": "da42d1b8-07e7-4849-b499-f97d292e2533",
                        "recipients": ["+254712345678"],
                        "metadata": {
                            "intention": "APPOINTMENT_REMINDER",
                            "owner": 50,
                            "source": "prod",
                            "service": "SLADE360_ADVANTAGE",
                        },
                    },
                    None,
                    None,
                    False,
                    True,
                )
            ]
        )
        sms = SMS.objects.all()
        segment_message_delivery_obj.refresh_from_db()

        assert sms.count() == 1
        assert segment_message_delivery_obj.sms is not None
        assert segment_message_delivery_obj.sms.state == "QUEUED"

    @override_settings(ENVIRONMENT="prod")
    @override_settings(SIL_COMMS_TRANSACTIONAL_SENDER_ID="BeWellApp")
    @patch(MOCK_ROOT + "LOGGER")
    @patch.object(ApiConnection, "call")
    @patch.object(
        ApiConnection,
        "credentials",
        create=True,
        new_callable=PicklableMagicMock,
    )
    @patch.object(ApiConnection, "authenticate")
    def test_send_sms_task_with_delivery_tracking_invalid_pk(
        self,
        mock_auth,
        mock_credz,
        mock_api_call,
        mock_logger,
    ):
        """Test sending a segment message with delivery tracking."""
        self.client.logout()

        def api_call(url, *args, **kwargs):
            if url == "/api/financial_accounts/accountsbalances/":
                return {
                    "results": [
                        {
                            "_identifiers": "bulk_sms_account",
                            "balance": "2500",
                        }
                    ],
                }
            elif url == "/api/billing/pricing_table_lines/":
                return {
                    "results": [
                        {
                            "organisation": "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
                            "billing_code": "APPOINTMENT_REMINDER_SMS",
                            "rate": "1.0",
                        }
                    ]
                }
            elif url == "/api/common/organisations/":
                return {
                    "results": [
                        {"id": "1107dee0-fa04-4187-a8e8-a4489141d13f"},
                    ],
                }

            return {
                "guid": "583cbe42-d987-4a05-b6b1-c2339f4551c0",
                "sender": "BeWellApp",
                "message": "New phone, who dis? [Test Message]",
                "recipients": ["+254712345678"],
                "state": "QUEUED",
                "sms": ["616d9996-4dc9-4909-a30d-e8a965a4dc7a"],
                "created": "2022-08-04 14:11:17.206377+03:00",
                "updated": "2022-08-04 14:11:17.206377+03:00",
            }

        mock_api_call.side_effect = api_call
        mock_credz.__getitem__.return_value = "435wersgfs45t"
        invalid_pk = uuid4()
        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"

        send_sms(
            "APPOINTMENT_REMINDER",
            "New phone, who dis?",
            ["+254712345678"],
            50,
            branch_id,
            "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
            model_name="segments.segmentmessagedelivery",
            model_obj_pk=invalid_pk,
        )

        mock_api_call.assert_has_calls(
            [
                call(
                    "v1/sms/bulk/",
                    "POST",
                    None,
                    {
                        "sender": "BeWellApp",
                        "message": "New phone, who dis?",
                        "app": "da42d1b8-07e7-4849-b499-f97d292e2533",
                        "recipients": ["+254712345678"],
                        "metadata": {
                            "intention": "APPOINTMENT_REMINDER",
                            "owner": 50,
                            "source": "prod",
                            "service": "SLADE360_ADVANTAGE",
                        },
                    },
                    None,
                    None,
                    False,
                    True,
                )
            ]
        )
        sms = SMS.objects.all()
        assert sms.count() == 1

        mock_logger.error.assert_called_once_with(
            (
                f"Object with ID {invalid_pk} of "
                f"type segments.segmentmessagedelivery does not exist."
            )
        )

    @override_settings(ENVIRONMENT="prod")
    @patch.object(ApiConnection, "call")
    @patch.object(
        ApiConnection,
        "credentials",
        create=True,
        new_callable=PicklableMagicMock,
    )
    @patch.object(ApiConnection, "authenticate")
    def test_send_sms_task_custom_transactional_sender_prod(
        self,
        mock_auth,
        mock_credz,
        mock_api_call,
    ):
        """Test sending an transactional SMS on production."""
        self.client.logout()

        def api_call(url, *args, **kwargs):
            if url == "/api/financial_accounts/accountsbalances/":
                return {
                    "results": [
                        {
                            "_identifiers": "bulk_sms_account",
                            "balance": "2500",
                        }
                    ],
                }
            elif url == "/api/billing/pricing_table_lines/":
                return {
                    "results": [
                        {
                            "organisation": "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
                            "billing_code": "APPOINTMENT_REMINDER_SMS",
                            "rate": "1.0",
                        }
                    ]
                }
            elif url == "/api/common/organisations/":
                return {
                    "results": [
                        {"id": "1107dee0-fa04-4187-a8e8-a4489141d13f"},
                    ],
                }

            return {
                "guid": "583cbe42-d987-4a05-b6b1-c2339f4551c0",
                "sender": "AccessAfyaInfo",
                "message": "New phone, who dis? [Test Message]",
                "recipients": ["+254712345678"],
                "state": "QUEUED",
                "sms": ["616d9996-4dc9-4909-a30d-e8a965a4dc7a"],
                "created": "2022-08-04 14:11:17.206377+03:00",
                "updated": "2022-08-04 14:11:17.206377+03:00",
            }

        mock_api_call.side_effect = api_call
        mock_credz.__getitem__.return_value = "435wersgfs45t"
        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"

        send_sms(
            "APPOINTMENT_REMINDER",
            "New phone, who dis?",
            ["+254712345678"],
            50,
            branch_id,
            "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
            sender_id=self.access_afya_sender.id,
        )

        mock_api_call.assert_has_calls(
            [
                call(
                    "v1/sms/bulk/",
                    "POST",
                    None,
                    {
                        "sender": "AccessAfyaInfo",
                        "message": "New phone, who dis?",
                        "app": "da42d1b8-07e7-4849-b499-f97d292e2533",
                        "recipients": ["+254712345678"],
                        "metadata": {
                            "intention": "APPOINTMENT_REMINDER",
                            "owner": 50,
                            "source": "prod",
                            "service": "SLADE360_ADVANTAGE",
                        },
                    },
                    None,
                    None,
                    False,
                    True,
                )
            ]
        )

        sms = SMS.objects.all()
        assert sms.count() == 1

        assert sms[0].sender.name == "AccessAfyaInfo"
        assert sms[0].message == "New phone, who dis?"
        assert sms[0].recipients == ["+254712345678"]
        assert sms[0].intention == "APPOINTMENT_REMINDER"
        assert sms[0].sil_comms_sms_id == UUID("616d9996-4dc9-4909-a30d-e8a965a4dc7a")

    @override_settings(ENVIRONMENT="prod")
    @patch.object(ApiConnection, "call")
    @patch.object(
        ApiConnection,
        "credentials",
        create=True,
        new_callable=PicklableMagicMock,
    )
    @patch.object(ApiConnection, "authenticate")
    def test_send_sms_task_custom_promotional_sender_prod(
        self,
        mock_auth,
        mock_credz,
        mock_api_call,
    ):
        """Test sending an transactional SMS on production."""
        self.client.logout()

        def api_call(url, *args, **kwargs):
            if url == "/api/financial_accounts/accountsbalances/":
                return {
                    "results": [
                        {
                            "_identifiers": "bulk_sms_account",
                            "balance": "2500",
                        }
                    ],
                }
            elif url == "/api/billing/pricing_table_lines/":
                return {
                    "results": [
                        {
                            "organisation": "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
                            "billing_code": "BROADCAST_SMS",
                            "rate": "1.0",
                        }
                    ]
                }
            elif url == "/api/common/organisations/":
                return {
                    "results": [
                        {"id": "1107dee0-fa04-4187-a8e8-a4489141d13f"},
                    ],
                }

            return {
                "guid": "583cbe42-d987-4a05-b6b1-c2339f4551c0",
                "sender": "AccessAfyaPromo",
                "message": "New phone, who dis? [Test Message]",
                "recipients": ["+254712345678"],
                "state": "QUEUED",
                "sms": ["616d9996-4dc9-4909-a30d-e8a965a4dc7a"],
                "created": "2022-08-04 14:11:17.206377+03:00",
                "updated": "2022-08-04 14:11:17.206377+03:00",
            }

        mock_api_call.side_effect = api_call
        mock_credz.__getitem__.return_value = "435wersgfs45t"
        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"

        send_sms(
            "BROADCAST",
            "New phone, who dis?",
            ["+254712345678"],
            50,
            branch_id,
            "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
            sender_id=self.access_afya_promo_sender.id,
        )

        mock_api_call.assert_has_calls(
            [
                call(
                    "v1/sms/bulk/",
                    "POST",
                    None,
                    {
                        "sender": "AccessAfyaPromo",
                        "message": "New phone, who dis?",
                        "app": "da42d1b8-07e7-4849-b499-f97d292e2533",
                        "recipients": ["+254712345678"],
                        "metadata": {
                            "intention": "BROADCAST",
                            "owner": 50,
                            "source": "prod",
                            "service": "SLADE360_ADVANTAGE",
                        },
                    },
                    None,
                    None,
                    False,
                    True,
                )
            ]
        )

        sms = SMS.objects.all()
        assert sms.count() == 1

        assert sms[0].sender.name == "AccessAfyaPromo"
        assert sms[0].message == "New phone, who dis?"
        assert sms[0].recipients == ["+254712345678"]
        assert sms[0].intention == "BROADCAST"
        assert sms[0].sil_comms_sms_id == UUID("616d9996-4dc9-4909-a30d-e8a965a4dc7a")

    def test_whitelisted_number_in_uat(self):
        """Test white listed numbers configuration is OK."""
        whitelisted_contacts = settings.WHITELISTED_TEST_RECIPIENTS
        assert "+254721570768" in whitelisted_contacts

    @override_settings(ENVIRONMENT="test")
    @override_settings(SIL_COMMS_PROMOTIONAL_SENDER_ID="BeWellInfo")
    @patch.object(ApiConnection, "call")
    @patch.object(
        ApiConnection,
        "credentials",
        create=True,
        new_callable=PicklableMagicMock,
    )
    @patch.object(ApiConnection, "authenticate")
    def test_send_sms_task_promotional_uat(
        self,
        mock_auth,
        mock_credz,
        mock_api_call,
    ):
        """Test sending an transactional SMS on UAT."""
        self.client.logout()

        def api_call(url, *args, **kwargs):
            if url == "/api/financial_accounts/accountsbalances/":
                return {
                    "results": [
                        {
                            "_identifiers": "bulk_sms_account",
                            "balance": "2500",
                        }
                    ],
                }
            elif url == "/api/billing/pricing_table_lines/":
                return {
                    "results": [
                        {
                            "organisation": "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
                            "billing_code": "BROADCAST_SMS",
                            "rate": "1.0",
                        }
                    ]
                }
            elif url == "/api/common/organisations/":
                return {
                    "results": [
                        {"id": "1107dee0-fa04-4187-a8e8-a4489141d13f"},
                    ],
                }

            return {
                "guid": "583cbe42-d987-4a05-b6b1-c2339f4551c0",
                "sender": "BeWellApp",
                "message": "New phone, who dis? [Test Message]",
                "recipients": ["+254721570768"],
                "state": "QUEUED",
                "sms": ["616d9996-4dc9-4909-a30d-e8a965a4dc7a"],
                "created": "2022-08-04 14:11:17.206377+03:00",
                "updated": "2022-08-04 14:11:17.206377+03:00",
            }

        mock_api_call.side_effect = api_call
        mock_credz.__getitem__.return_value = "435wersgfs45t"
        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"

        send_sms(
            "BROADCAST",
            "New phone, who dis?",
            ["+254721570768"],
            50,
            branch_id,
            "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
        )
        mock_api_call.assert_has_calls(
            [
                call(
                    "v1/sms/bulk/",
                    "POST",
                    None,
                    {
                        "sender": "BeWellInfo",
                        "message": "New phone, who dis? [Test Message]",
                        "app": "da42d1b8-07e7-4849-b499-f97d292e2533",
                        "recipients": ["+254721570768"],
                        "metadata": {
                            "intention": "BROADCAST",
                            "owner": 50,
                            "source": "test",
                            "service": "SLADE360_ADVANTAGE",
                        },
                    },
                    None,
                    None,
                    False,
                    True,
                )
            ]
        )

        sms = SMS.objects.all()
        assert sms.count() == 1

        assert sms[0].sender.name == "BeWellInfo"
        assert sms[0].message == "New phone, who dis? [Test Message]"
        assert sms[0].recipients == ["+254721570768"]
        assert sms[0].intention == "BROADCAST"
        assert sms[0].sil_comms_sms_id == UUID("616d9996-4dc9-4909-a30d-e8a965a4dc7a")

    @override_settings(ENVIRONMENT="test")
    @override_settings(SIL_COMMS_PROMOTIONAL_SENDER_ID="BeWellInfo")
    @patch.object(ApiConnection, "call")
    @patch.object(
        ApiConnection,
        "credentials",
        create=True,
        new_callable=PicklableMagicMock,
    )
    @patch.object(ApiConnection, "authenticate")
    def test_send_sms_task_promotional_uat_non_whitelisted_number(
        self,
        mock_auth,
        mock_credz,
        mock_api_call,
    ):
        """Test sending an transactional SMS on UAT for non whitelisted nos."""
        self.client.logout()

        def api_call(url, *args, **kwargs):
            if url == "/api/financial_accounts/accountsbalances/":
                return {
                    "results": [
                        {
                            "_identifiers": "bulk_sms_account",
                            "balance": "2500",
                        }
                    ],
                }
            elif url == "/api/billing/pricing_table_lines/":
                return {
                    "results": [
                        {
                            "organisation": "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
                            "billing_code": "BROADCAST_SMS",
                            "rate": "1.0",
                        }
                    ]
                }
            elif url == "/api/common/organisations/":
                return {
                    "results": [
                        {"id": "1107dee0-fa04-4187-a8e8-a4489141d13f"},
                    ],
                }

            return {
                "guid": "583cbe42-d987-4a05-b6b1-c2339f4551c0",
                "sender": "BeWellApp",
                "message": "New phone, who dis? [Test Message]",
                "recipients": ["+254722000000"],
                "state": "QUEUED",
                "sms": ["616d9996-4dc9-4909-a30d-e8a965a4dc7a"],
                "created": "2022-08-04 14:11:17.206377+03:00",
                "updated": "2022-08-04 14:11:17.206377+03:00",
            }

        mock_api_call.side_effect = api_call
        mock_credz.__getitem__.return_value = "435wersgfs45t"
        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"

        send_sms(
            "BROADCAST",
            "New phone, who dis?",
            ["+254722000000"],
            50,
            branch_id,
            "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
        )
        call_to_send = call(
            "v1/sms/bulk/",
            "POST",
            None,
            {
                "sender": "BeWellInfo",
                "message": "New phone, who dis? [Test Message]",
                "app": "da42d1b8-07e7-4849-b499-f97d292e2533",
                "recipients": ["+254721570768"],
                "metadata": {
                    "intention": "BROADCAST",
                    "owner": 50,
                    "source": "test",
                    "service": "SLADE360_ADVANTAGE",
                },
            },
            None,
            None,
            False,
            True,
        )
        assert call_to_send not in mock_api_call.call_args_list

        sms = SMS.objects.all()
        assert sms.count() == 0

    @override_settings(ENVIRONMENT="test")
    @patch(MOCK_ROOT + "LOGGER")
    @patch.object(ApiConnection, "call")
    @patch.object(
        ApiConnection,
        "credentials",
        create=True,
        new_callable=PicklableMagicMock,
    )
    @patch.object(ApiConnection, "authenticate")
    def test_send_sms_task_no_balance(
        self,
        mock_auth,
        mock_credz,
        mock_api_call,
        mock_logger,
    ):
        """Test sending an with no balance available."""
        self.client.logout()

        def api_call(url, *args, **kwargs):
            if url == "/api/financial_accounts/accountsbalances/":
                return {
                    "results": [
                        {
                            "_identifiers": "bulk_sms_account",
                            "balance": "0",
                        }
                    ],
                }
            elif url == "/api/billing/pricing_table_lines/":
                return {
                    "results": [
                        {
                            "organisation": "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
                            "billing_code": "BROADCAST_SMS",
                            "rate": "1.0",
                        }
                    ]
                }
            elif url == "/api/common/organisations/":
                return {
                    "results": [
                        {"id": "1107dee0-fa04-4187-a8e8-a4489141d13f"},
                    ],
                }

        mock_api_call.side_effect = api_call
        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"

        send_sms(
            "BROADCAST",
            "New phone, who dis?",
            ["+254712345678"],
            50,
            branch_id,
            "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
        )

        mock_logger.error.assert_called_once_with(
            "Bulk SMS wallet doesn't have enough balance"
        )

    @override_settings(ENVIRONMENT="test")
    @patch(MOCK_ROOT + "LOGGER")
    @patch("sil_advantage.billing.utils.get_wallet_balances")
    @patch("sil_advantage.notifications.sms.tasks.can_send_sms")
    @patch.object(Organisation, "objects")
    @patch.object(ApiConnection, "call")
    @patch.object(
        ApiConnection,
        "credentials",
        create=True,
        new_callable=PicklableMagicMock,
    )
    @patch.object(ApiConnection, "authenticate")
    def test_send_sms_task_no_wallet(
        self,
        mock_auth,
        mock_credz,
        mock_api_call,
        mock_org_objects,
        mock_can_send_sms,
        mock_get_wallet_balances,
        mock_logger,
    ):
        """Test sending SMS with no wallets."""
        self.client.logout()

        mock_api_call.return_value = {"results": []}
        mock_get_wallet_balances.return_value = None

        mock_org = Mock()
        mock_org.customer_id = "f42cb5d2-3d6b-43a6-8b79-0406cba00e86"
        mock_org_objects.get.return_value = mock_org

        mock_can_send_sms.return_value = (
            False,
            "No bulk SMS wallet exists",
            0,
            0,
            None,
        )

        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"
        customer_id = "f42cb5d2-3d6b-43a6-8b79-0406cba00e86"

        send_sms(
            "BROADCAST",
            "New phone, who dis? 👀",
            ["+254712345678"],
            50,
            branch_id,
            customer_id,
        )

        mock_logger.error.assert_called_once_with("No bulk SMS wallet exists")

    @override_settings(ENVIRONMENT="test")
    @patch(MOCK_ROOT + "LOGGER")
    @patch.object(ApiConnection, "call")
    @patch.object(
        ApiConnection,
        "credentials",
        create=True,
        new_callable=PicklableMagicMock,
    )
    @patch.object(ApiConnection, "authenticate")
    def test_send_sms_task_missing_pricing(
        self,
        mock_auth,
        mock_credz,
        mock_api_call,
        mock_logger,
    ):
        """Test sending an SMS with missing pricing information."""
        self.client.logout()

        def api_call(url, *args, **kwargs):
            if url == "/api/financial_accounts/accountsbalances/":
                return {
                    "results": [
                        {
                            "_identifiers": "bulk_sms_account",
                            "balance": "100",
                        }
                    ],
                }
            elif url == "/api/billing/pricing_table_lines/":
                # Simulate missing pricing information
                return {"results": []}

            elif url == "/api/common/organisations/":
                return {
                    "results": [
                        {"id": "1107dee0-fa04-4187-a8e8-a4489141d13f"},
                    ],
                }

        mock_api_call.side_effect = api_call
        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"

        send_sms(
            "BROADCAST",
            "New phone, who dis?",
            ["+254712345678"],
            50,
            branch_id,
            "f42cb5d2-3d6b-43a6-8b79-0406cba00e86",
        )
        mock_logger.error.assert_called_once_with(
            "Error fetching pricing information: No pricing information found"
        )

    def test_process_delivery_report_task(self):
        """Test processing a delivery report from SIL Comms."""
        sms = baker.make(
            SMS,
            organisation=global_organisation(),
            sender=self.access_afya_sender,
            message="Hi there",
            recipients=["+254722345678"],
            intention="BROADCAST",
            sil_comms_sms_id=UUID("616d9996-4dc9-4909-a30d-e8a965a4dc7a"),
        )
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
        process_delivery_report(payload=payload)

        sms.refresh_from_db()
        assert sms.state == payload["data"]["state"]

        payload["status"] = "error"
        payload["data"]["state"] = "FAILED"
        payload["message"] = "COULD_NOT_ROUTE"

        process_delivery_report(payload=payload)
        sms.refresh_from_db()

        assert sms.state == "FAILED"
        assert sms.failure_reason == "COULD_NOT_ROUTE"

    @patch(MOCK_ROOT + "LOGGER")
    def test_process_delivery_report_task_sms_not_found(self, mock_logger):
        """Test processing a delivery report from SIL Comms for non-existent SMS."""
        sil_comms_sms_id = uuid4()
        payload = {
            "status": "success",
            "message": "SUCCESS",
            "type": "DELIVERY_REPORT",
            "data": {
                "guid": sil_comms_sms_id,
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
        process_delivery_report(payload=payload)
        mock_logger.warning.assert_called_once_with(
            f"SMS object with sil_comms_id {sil_comms_sms_id} does not exist."
        )

    def test_process_interactive_shortcode_task(self):
        """Test the process_interactive_shortcode Celery task."""
        payload = {
            "Msisdn": "+254722345678",
            "Shortcode": "232435",
            "Response": "Test Message",
        }

        sender_obj = baker.make(
            SenderID,
            name="232435",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
        )
        baker.make(
            SMS,
            organisation=global_organisation(),
            sender=sender_obj,
            message="Hi there",
            recipients=["+254722345678"],
            intention="BROADCAST",
            delivery_type="OUTBOUND",
            **self.workstation_data,
        )

        process_interactive_shortcode(payload)

        sms = SMS.objects.filter().latest("created")
        self.assertIsNotNone(sms)
        self.assertEqual(sms.sender, sender_obj)
        self.assertEqual(sms.delivery_type, "INBOUND")
        self.assertEqual(sms.recipients, ["+254722345678"])
        self.assertEqual(sms.message, "Test Message")
        self.assertEqual(sms.intention, "DIRECT_MESSAGE")

    @patch(MOCK_ROOT + "LOGGER")
    def test_process_interactive_shortcode_last_sms_not_found(self, mock_logger):
        """Test the case where SenderID does not exist (SenderID.DoesNotExist)."""
        payload = {
            "Msisdn": "+254722345678",
            "Shortcode": "232435",
            "Response": "Test Message",
        }

        process_interactive_shortcode(payload)

        mock_logger.warning.assert_called_once_with(
            "Latest SMS sent using Shortcode 232435 to +254722345678 not found."
        )

        # Ensure no SMS object was created
        sms = SMS.objects.last()
        self.assertIsNone(sms)

    def test_generate_sms_log_report_no_records(self):
        """Test generating an sms log report."""
        date_to = date(2022, 5, 12)
        date_from = date(2022, 5, 13)
        sms_report_obj = baker.make(
            SMSLogReport,
            **self.workstation_data,
        )
        payload = {
            "delivery_type": "OUTBOUND",
            "date_from": date_from,
            "date_to": date_to,
        }

        generate_sms_log_report(payload=payload, sms_report_id=sms_report_obj.id)
        sms_report_obj.refresh_from_db()
        assert sms_report_obj.process_state == ProcessState.FAILED
        assert sms_report_obj.failure_reason == "No SMS's found within the give period."

    def test_generate_sms_log_report(self):
        """Test generating an sms log report."""
        date_from = date(2023, 1, 1)
        date_to = date.today()

        sms_report_obj = baker.make(
            SMSLogReport,
            organisation=global_organisation(),
            **self.workstation_data,
        )
        baker.make(
            SMS,
            organisation=global_organisation(),
            sender=self.access_afya_sender,
            message="Hi there",
            recipients=["+254722345678"],
            intention="BROADCAST",
            delivery_type="INBOUND",
            **self.workstation_data,
        )
        baker.make(
            SMS,
            organisation=global_organisation(),
            sender=self.access_afya_sender,
            message="Hello again",
            recipients=["+254722345678"],
            intention="BROADCAST",
            delivery_type="OUTBOUND",
            **self.workstation_data,
        )
        payload = {
            "delivery_type": "OUTBOUND",
            "date_from": date_from,
            "date_to": date_to,
        }

        generate_sms_log_report(payload=payload, sms_report_id=sms_report_obj.id)
        sms_report_obj.refresh_from_db()

        assert sms_report_obj.process_state == ProcessState.COMPLETE
        assert sms_report_obj.report_file is not None

        # test with no delivery_type filter
        sms_report_obj_two = baker.make(
            SMSLogReport,
            organisation=global_organisation(),
            **self.workstation_data,
        )
        payload = {
            "date_from": date_from,
            "date_to": date_to,
        }

        generate_sms_log_report(payload=payload, sms_report_id=sms_report_obj_two.id)
        sms_report_obj_two.refresh_from_db()

        assert sms_report_obj.process_state == ProcessState.COMPLETE
        assert sms_report_obj.report_file is not None
