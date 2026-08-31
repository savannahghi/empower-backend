"""Handles organisation operating regions functionalities.

Classes:
    RegionManager: Provides methods to get operating regions within an organisation.
"""
from typing import List

from sil_advantage.common.models import OperatingRegion
from sil_advantage.notifications.models import USSDCode


class RegionManager:
    """Provides methods to get operating regions within an organisation."""

    def __init__(
        self,
    ) -> None:
        """Initialize."""
        pass

    @staticmethod
    def get_operating_regions(ussd_code: str) -> List[str]:
        """Return the names of operating regions within the organisation."""
        code = USSDCode.objects.get(ussd_code=ussd_code)
        organisation = code.organisation
        regions = OperatingRegion.objects.filter(organisation=organisation)
        region_names = [region.name for region in regions]
        return region_names
