"""Patient filters."""
import django_filters

from sil_advantage.common.filters.base import CommonFieldsFilterset, ListFilter
from sil_advantage.patients.models import (
    Patient,
    PatientCover,
    PatientDocument,
    PatientListUpload,
)


class PatientFilter(CommonFieldsFilterset):
    """Filter patients."""

    created = django_filters.DateFromToRangeFilter()
    date_of_birth = django_filters.DateFromToRangeFilter(
        field_name="person__date_of_birth"
    )

    class Meta:
        """Define filter options."""

        model = Patient
        fields = "__all__"


class PatientDocumentAttachmentFilter(CommonFieldsFilterset):
    """Filter patient document attachments."""

    document_type = ListFilter()
    document_status = ListFilter()

    class Meta:
        """Define filter options."""

        model = PatientDocument
        exclude = (
            "data",
            "metadata",
        )


class PatientCoverFilter(CommonFieldsFilterset):
    """Filter patientcover."""

    class Meta:
        """Define filter options."""

        model = PatientCover
        fields = "__all__"


class PatientListUploadFilter(CommonFieldsFilterset):
    """Filter patient list uploads."""

    class Meta:
        """Define filter options."""

        model = PatientListUpload
        exclude = ("mapping",)
