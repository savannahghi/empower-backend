"""Tests for USSD models."""
import pytest
from model_bakery import baker

from sil_advantage.common.models.organisation_models import Organisation
from sil_advantage.notifications.models import USSDCode


@pytest.mark.django_db
class TestUSSDCode:
    """Tests for USSDCode model."""

    def setup_method(self):
        """Setup test environment."""
        self.organisation = baker.make(Organisation, organisation_name="AccessAfya")

    def test_create_ussd_code(self):
        """Test creating a USSD code."""
        ussd_code = baker.make(
            USSDCode,
            ussd_code="*393#",
            gateway="SAFARICOM",
            type="PREPAID",
            organisation=self.organisation,
        )
        assert ussd_code.ussd_code == "*393#"
        assert ussd_code.gateway == "SAFARICOM"
        assert ussd_code.type == "PREPAID"
        assert ussd_code.organisation == self.organisation

    def test_unicode_representation(self):
        """Test string representation of USSDCode."""
        ussd_code = baker.make(
            USSDCode, ussd_code="*393#", organisation=self.organisation
        )
        assert str(ussd_code) == "*393#"

    def test_get_org_ussd_codes(self):
        """Test retrieving an organisation's USSD codes."""
        ussd_code1 = baker.make(
            USSDCode,
            ussd_code="*393#",
            gateway="SAFARICOM",
            type="PREPAID",
            organisation=self.organisation,
        )
        ussd_code2 = baker.make(
            USSDCode,
            ussd_code="*393*5113#",
            gateway="SAFARICOM",
            type="POSTPAID",
            organisation=self.organisation,
        )

        ussd_codes = USSDCode.get_org_ussd_codes(self.organisation)
        assert ussd_codes.count() == 2
        assert ussd_code1 in ussd_codes
        assert ussd_code2 in ussd_codes
