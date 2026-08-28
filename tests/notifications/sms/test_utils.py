"""Test SMS utils."""
from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import override_settings
from model_bakery import baker

from sil_advantage.common.models.common_models import Person, PersonContact
from sil_advantage.notifications.sms.models import SenderID
from sil_advantage.notifications.sms.utils import (
    can_send_sms,
    create_sms_from_template,
    get_sms_parts,
    send_custom_sms,
)
from sil_advantage.settings.models import OrganisationSetting
from tests.common.test_common_views import LoggedInMixin


@pytest.mark.usefixtures("default_transactional_sender")
class SMSUtilsTestCase(LoggedInMixin):
    """Test SMS utils."""

    def setUp(self):
        """Update test environment."""
        super().setUp()
        OrganisationSetting.set_org_setting(
            self.global_organisation,
            "sms:appointment_reminder_en_template",
            (
                "Hi {first_name} {last_name}! "
                "You booked an appointment for {time} "
                "at {provider}."
            ),
        )
        OrganisationSetting.set_branch_setting(
            self.global_organisation,
            "abf685c2-9cc5-4d17-aa81-9944a0f590fa",
            "sms:appointment_creation_en_template",
            (
                "Dear {last_name}, an appointment at {provider} "
                "for {specialty} has been created."
            ),
        )
        self.default_transactional_sender = SenderID.objects.filter(
            name="BeWellApp"
        ).latest("created")

    @override_settings(ENVIRONMENT="prod")
    def test_create_sms_from_template(self):
        """Test creating an SMS from an SMS Template."""
        person = baker.make(
            Person,
            first_name="Paul",
            last_name="Atreides",
            title="Duke",
            language="en",
            created_by=uuid4(),
            organisation=self.global_organisation,
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
        )
        sms = create_sms_from_template(
            "APPOINTMENT_REMINDER",
            "+254712345678",
            self.global_organisation,
            "abf685c2-9cc5-4d17-aa81-9944a0f590fa",
            person,
            first_name="Jane",
            last_name="Doe",
            time="1st Dec 16:42",
            provider="Hospitali",
        )
        assert sms["intention"] == "APPOINTMENT_REMINDER"
        assert sms["recipients"] == ["+254712345678"]
        assert sms["message"] == (
            "Hi Jane Doe! You booked an appointment for 1st Dec 16:42 at Hospitali."
        )

    @override_settings(ENVIRONMENT="prod")
    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_send_custom_with_consent(self, mock_send_sms):
        """Test sending custom sms with consent."""
        phone_number = "+254799757242"
        sms_intention = "APPOINTMENT_REMINDER"
        first_name = "Jane"
        last_name = "Doe"
        time = "1st Dec 16:42"
        provider = "Hospitali"
        organisation = self.global_organisation
        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"

        # create a person
        person = Person.objects.create(
            first_name=first_name,
            last_name=last_name,
            organisation=organisation,
            created_by=uuid4(),
            updated_by=uuid4(),
        )
        PersonContact.objects.create(
            person=person,
            contact_type="phone_number",
            contact=phone_number,
            consent_to_contact_given=True,
            organisation=organisation,
            created_by=uuid4(),
            updated_by=uuid4(),
        )

        # call the send_custom_sms function
        send_custom_sms(
            sms_intention,
            phone_number,
            self.global_organisation,
            branch_id,
            person,
            priority=settings.CELERY_TASK_LOW_PRIORITY,
            first_name=first_name,
            last_name=last_name,
            time=time,
            provider=provider,
        )
        mock_send_sms.assert_called_with(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_LOW_PRIORITY,
            args=(
                sms_intention,
                (
                    "Hi Jane Doe! You booked an appointment for "
                    "1st Dec 16:42 at Hospitali."
                ),
                [phone_number],
                self.global_organisation.slade_code,
                branch_id,
                None,
            ),
            kwargs={"sender_id": self.default_transactional_sender.id},
        )

    @override_settings(ENVIRONMENT="prod")
    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_send_custom_without_consent(self, mock_send_sms):
        """Test sending custom sms without consent."""
        phone_number = "+254799757242"
        sms_intention = "APPOINTMENT_REMINDER"
        first_name = "Jane"
        last_name = "Doe"
        time = "1st Dec 16:42"
        provider = "Hospitali"
        organisation = self.global_organisation
        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"

        # create a person
        person = Person.objects.create(
            first_name=first_name,
            last_name=last_name,
            organisation=organisation,
            created_by=uuid4(),
            updated_by=uuid4(),
        )
        PersonContact.objects.create(
            person=person,
            contact_type="phone_number",
            contact=phone_number,
            consent_to_contact_given=False,
            organisation=organisation,
            created_by=uuid4(),
            updated_by=uuid4(),
        )

        # call the send_custom_sms function
        send_custom_sms(
            sms_intention,
            phone_number,
            self.global_organisation,
            branch_id,
            person,
            priority=settings.CELERY_TASK_LOW_PRIORITY,
            first_name=first_name,
            last_name=last_name,
            time=time,
            provider=provider,
        )
        mock_send_sms.assert_not_called()

    @override_settings(ENVIRONMENT="prod")
    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_send_custom_without_phone_number(self, mock_send_sms):
        """Test sending custom sms without phone_number."""
        sms_intention = "APPOINTMENT_REMINDER"
        first_name = "Jane"
        last_name = "Doe"
        time = "1st Dec 16:42"
        provider = "Hospitali"
        organisation = self.global_organisation
        branch_id = "abf685c2-9cc5-4d17-aa81-9944a0f590fa"

        # create a person
        person = Person.objects.create(
            first_name=first_name,
            last_name=last_name,
            organisation=organisation,
            created_by=uuid4(),
            updated_by=uuid4(),
        )

        # call the send_custom_sms function
        send_custom_sms(
            sms_intention,
            "",
            self.global_organisation,
            branch_id,
            person,
            priority=settings.CELERY_TASK_LOW_PRIORITY,
            first_name=first_name,
            last_name=last_name,
            time=time,
            provider=provider,
        )
        mock_send_sms.assert_not_called()

    def test_get_sms_parts_gsm(self):
        """Test get_sms_parts for a message using GSM charset."""
        message = "Hello, this is a test message!"
        expected_parts = 1
        n_parts = get_sms_parts(message)

        assert n_parts == expected_parts

    @patch("sil_advantage.billing.utils.get_wallet_balances")
    @patch("sil_advantage.common.api_clients.erp.fetch_from_erp_cache")
    def test_can_send_sms_multiple_parts(self, mock_erp_cache, mock_wallet_balances):
        """Test can_send_sms when message has multiple parts."""
        mock_wallet_balances.return_value = {
            "bulk_sms_account": {"balance": Decimal("1000.00")}
        }
        mock_erp_cache.side_effect = [
            {"id": "some_org_id"},
            {"results": [{"rate": "1.00"}]},
        ]

        org = Mock()
        org.slade_code = "test_slade_code"

        message = "This is a long message 😊" * 5

        can_send, err, n_parts, estimated_cost, wallets = can_send_sms(
            org,
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
            intention="DIRECT_MESSAGE",
            message=message,
            n_recipients=1,
        )

        assert can_send is True
        assert n_parts == 2
        assert estimated_cost == Decimal("2.00")
