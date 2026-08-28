"""Segments filters."""

from sil_advantage.common.filters.base import CommonFieldsFilterset
from sil_advantage.prescriptions.models import Prescription


class PrescriptionFilter(CommonFieldsFilterset):
    """Prescription filter."""

    class Meta:
        """Filter options."""

        model = Prescription
        fields = "__all__"
