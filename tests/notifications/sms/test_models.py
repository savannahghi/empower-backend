"""Test sms models."""
from datetime import datetime, timedelta

import pytest
import time_machine
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone
from model_bakery import baker

from sil_advantage.common.models.organisation_models import Organisation
from sil_advantage.notifications.sms.models import SMS, SenderID
from tests.common.test_common_views import LoggedInMixin, global_organisation


@pytest.mark.usefixtures("organisation")
class TestSenderID(LoggedInMixin):
    """Tests for SenderID."""

    def setUp(self):
        """Setup test environment."""
        self.test_org = baker.make(Organisation, organisation_name="AccessAfya")
        self.metadata = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }
        baker.make(
            SenderID,
            name="Slade360Adv",
            sender_type="PROMOTION",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            organisation=self.global_organisation,
            active=True,
        )
        baker.make(
            SenderID,
            name="BeWellApp",
            sender_type="TRANSACTION",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            organisation=self.global_organisation,
            active=True,
        )

        self.organisation = global_organisation()
        super().setUp()

    def test_unicode(self):
        """Test for unicode."""
        sender_id = baker.make(
            SenderID,
            name="Slade360",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30),
            organisation=self.global_organisation,
            active=True,
        )

        expected_value = sender_id.name
        assert str(sender_id) == expected_value

    def test_validate_start_date_is_before_end_date(self):
        """Test validate creating a sender with invalid dates."""
        expected_error = "SenderID end date must be greater than the start date."
        with pytest.raises(ValidationError, match=expected_error):
            baker.make(
                SenderID,
                name="Slade360",
                start_date=timezone.now(),
                end_date=timezone.now() - timedelta(days=30),
                organisation=self.global_organisation,
                active=True,
            )
        sender_id_exists = SenderID.objects.filter(name="Slade360").exists()
        assert sender_id_exists is False

    def test_validate_start_date_not_in_the_future(self):
        """Validate SenderID start date is not in the future."""
        expected_error = "SenderID start date cannot be in the future."
        with pytest.raises(ValidationError, match=expected_error):
            baker.make(
                SenderID,
                name="Slade360",
                start_date=timezone.now() + timedelta(days=10),
                end_date=timezone.now() + timedelta(days=30),
                organisation=self.global_organisation,
                active=True,
            )
        sender_id_exists = SenderID.objects.filter(name="Slade360").exists()
        assert sender_id_exists is False

    def test_validate_end_date_not_in_the_past(self):
        """Validate SenderID end date is not in the past."""
        expected_error = "SenderID end date cannot be in the past."
        with pytest.raises(ValidationError, match=expected_error):
            baker.make(
                SenderID,
                name="Slade360",
                start_date=timezone.now() - timedelta(days=10),
                end_date=timezone.now() - timedelta(days=5),
                organisation=self.global_organisation,
                active=True,
            )
        sender_id_exists = SenderID.objects.filter(name="Slade360").exists()
        assert sender_id_exists is False

    def test_get_org_sender_ids(self):
        """Test getting an orgs custom sender ids."""
        baker.make(
            SenderID,
            name="AccessAfya",
            sender_type="TRANSACTION",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            organisation=self.test_org,
            active=True,
            **self.metadata,
        )
        baker.make(
            SenderID,
            name="AccessAfyaInfo",
            sender_type="PROMOTION",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
            organisation=self.test_org,
            active=True,
            **self.metadata,
        )
        # get transactional senders
        transactional_senders = SenderID.get_org_sender_ids(
            organisation=self.test_org,
            sender_type="TRANSACTION",
            branch_id=self.metadata["branch_id"],
        )

        assert transactional_senders.count() == 1
        assert transactional_senders.first().name == "AccessAfya"

        # get promotional senders
        promotional_senders = SenderID.get_org_sender_ids(
            organisation=self.test_org,
            sender_type="PROMOTION",
            branch_id=self.metadata["branch_id"],
        )

        assert promotional_senders.count() == 1
        assert promotional_senders.first().name == "AccessAfyaInfo"

    @override_settings(SIL_COMMS_TRANSACTIONAL_SENDER_ID="BeWellApp")
    @override_settings(SIL_COMMS_PROMOTIONAL_SENDER_ID="Slade360Adv")
    def test_get_org_sender_ids_without_custom_sender_configuration(self):
        """Test get an orgs sender ids with no custom configuration."""
        # get transactional senders
        transactional_senders = SenderID.get_org_sender_ids(
            organisation=self.test_org,
            sender_type="TRANSACTION",
            branch_id=self.metadata["branch_id"],
        )

        assert transactional_senders.count() == 1
        assert transactional_senders.first().name == "BeWellApp"

        # get promotional senders
        promotional_senders = SenderID.get_org_sender_ids(
            organisation=self.test_org,
            sender_type="PROMOTION",
            branch_id=self.metadata["branch_id"],
        )

        assert promotional_senders.count() == 1
        assert promotional_senders.first().name == "Slade360Adv"

    def test_transactional_disabled_sender_ids(self):
        """Test a disabled sender ID."""
        transactional = SenderID.objects.filter(name="BeWellApp").first()
        assert transactional.disabled["status"] is False
        assert transactional.disabled["reason"] is None

    def test_promotional_disabled_sender_ids(self):
        """Test a disabled sender ID."""
        # Local time: 10:00 pm
        with time_machine.travel(datetime(year=1999, month=12, day=13, hour=19)):
            promotional = SenderID.objects.filter(name="Slade360Adv").first()
            assert promotional.disabled["status"] is True
            assert (
                promotional.disabled["reason"]
                == "This option is only available from 8:00 AM to 6:00 PM."
            )

        # Local time: 08:00
        with time_machine.travel(datetime(year=1999, month=6, day=12, hour=14)):
            promotional = SenderID.objects.filter(name="Slade360Adv").first()
            assert promotional.disabled["status"] is False
            assert promotional.disabled["reason"] is None

    def test_inbound_sms_from_to_fields(self):
        """Test that from_field and to_field for inbound SMS are correct."""
        sender = baker.make(
            SenderID,
            name="AccessAfya",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
        )
        sms = baker.make(
            SMS,
            sender=sender,
            recipients=["+254712345678"],
            delivery_type="INBOUND",
        )
        assert sms.from_name == "+254712345678"
        assert sms.to == "AccessAfya"

    def test_outbound_sms_from_to_fields(self):
        """Test that from_field and to_field for outbound SMS are correct."""
        sender = baker.make(
            SenderID,
            name="AccessAfya",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
        )
        sms = baker.make(
            SMS,
            sender=sender,
            recipients=["+254717356476"],
            delivery_type="OUTBOUND",
        )
        assert sms.from_name == "AccessAfya"
        assert sms.to == "+254717356476"

    def test_inbound_sms_no_recipients(self):
        """Test that from_field returns None for inbound SMS with invalid recipients."""
        sender = baker.make(
            SenderID, name="AccessAfya", end_date=timezone.now() + timedelta(days=90)
        )
        sms = baker.make(
            SMS,
            sender=sender,
            recipients=["INVALID"],
            delivery_type="INBOUND",
        )
        assert sms.from_name == "INVALID"
        assert sms.to == "AccessAfya"

    def test_outbound_sms_no_sender(self):
        """Test that from_field returns None ."""
        sms = baker.make(
            SMS,
            sender=None,
            recipients=["+254712345678"],
            delivery_type="OUTBOUND",
        )
        assert sms.from_name is None
        assert sms.to == "+254712345678"
