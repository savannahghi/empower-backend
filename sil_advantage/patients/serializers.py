"""Patient serializers."""
from rest_framework import serializers

from sil_advantage.common.serializers import (
    BaseSerializer,
    PersonSerializer,
    WritabledNestedBaseSerializer,
)
from sil_advantage.patients.models import (
    DocumentTransitionLog,
    Patient,
    PatientCover,
    PatientDocument,
    PatientListUpload,
)
from sil_advantage.sil_auth.models import SILUser


class PatientSerializer(WritabledNestedBaseSerializer):
    """Patient serializer."""

    patient_id = serializers.ReadOnlyField()
    file_number = serializers.ReadOnlyField()
    customer_id = serializers.ReadOnlyField()
    person = PersonSerializer()
    vitals_reference_ranges = serializers.ReadOnlyField()

    class Meta:
        """Serialization options."""

        model = Patient
        fields = "__all__"


class DocumentTransitionLogSerializer(BaseSerializer):
    """DocumentTransitionLog Serializer."""

    class Meta:
        """Serialization options."""

        model = DocumentTransitionLog
        fields = "__all__"


class PatientDocumentSerializer(BaseSerializer):
    """Serialize patient document attachment."""

    file_number = serializers.ReadOnlyField(source="patient.file_number")
    patient_name = serializers.ReadOnlyField(source="patient.person.get_full_name")

    class Meta:
        """Define serialization options."""

        model = PatientDocument
        fields = "__all__"


class PatientHealthIDSerializer(serializers.Serializer):
    """Serialize patient health ID."""

    profile_id = serializers.CharField()
    health_id = serializers.CharField()


class PatientListUploadSerializer(BaseSerializer):
    """PatientListUpload Serializer."""

    file_name = serializers.CharField(source="upload_file.title", read_only=True)
    upload_file_url = serializers.URLField(
        source="upload_file.data.url", read_only=True
    )
    failed_upload_file_url = serializers.URLField(
        source="failed_uploads_file.data.url", read_only=True
    )
    uploaded_by = serializers.SerializerMethodField(read_only=True)

    class Meta:
        """Define serialization options."""

        model = PatientListUpload
        fields = "__all__"

    def get_uploaded_by(self, obj: PatientListUpload) -> str | None:
        """Serialize the created_by field."""
        try:
            user = SILUser.objects.get(guid=obj.created_by)
            return user.get_full_name()
        except SILUser.DoesNotExist:
            return None


class PatientCoverSerializer(BaseSerializer):
    """Serialize patient cover."""

    patient_name = serializers.ReadOnlyField(source="patient.person.get_full_name")

    class Meta:
        """Define serialization options."""

        model = PatientCover
        fields = "__all__"
