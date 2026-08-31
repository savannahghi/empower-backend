"""Test case for operation region manager."""

from model_bakery import baker

from sil_advantage.common.models import OperatingRegion
from sil_advantage.notifications.models import USSDCode
from sil_advantage.notifications.ussd.managers.operation_region_manager import (
    RegionManager,
)
from sil_advantage.sil_auth.models import SILUser
from tests.common.test_common_views import LoggedInMixin


class RegionManagerTestCase(LoggedInMixin):
    """Test case for RegionManager class."""

    def setUp(self):
        """Set up the test case with initial data."""
        super().setUp()
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.organisation = self.global_organisation
        # Create a USSDCode for the organisation
        self.ussd_code = USSDCode.objects.create(
            ussd_code="*123#",
            gateway="SAFARICOM",
            type="PREPAID",
            organisation=self.organisation,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        # Create some operating regions for the organisation
        self.region1 = OperatingRegion.objects.create(
            name="Region 1",
            unit_type="COUNTY",
            country="KEN",
            created_by=self.user.pk,
            updated_by=self.user.pk,
            organisation=self.organisation,
        )
        self.region2 = OperatingRegion.objects.create(
            name="Region 2",
            unit_type="COUNTY",
            country="KEN",
            created_by=self.user.pk,
            updated_by=self.user.pk,
            organisation=self.organisation,
        )
        # Create an instance of RegionManager
        self.region_manager = RegionManager()

    def test_get_operating_regions(self):
        """Test the get_operating_regions method."""
        regions = self.region_manager.get_operating_regions(self.ussd_code.ussd_code)
        self.assertEqual(len(regions), 2)
        self.assertIn("Region 1", regions)
        self.assertIn("Region 2", regions)
