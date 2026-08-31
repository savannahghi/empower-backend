"""Practitioner app filters."""
from sil_advantage.common.filters.base import CommonFieldsFilterset
from sil_advantage.practitioners.models import Practitioner


class Practitionerfilter(CommonFieldsFilterset):
    """Filter practitioners."""

    class Meta:
        """Setup filter options."""

        model = Practitioner
        fields = "__all__"
