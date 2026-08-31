"""Visits serializers."""
from typing import Optional

from rest_framework import serializers

from sil_advantage.billing.serializers import (
    ClinicalOrderSerializer,
    InvoiceSerializer,
)
from sil_advantage.common.serializers import BaseSerializer
from sil_advantage.visits.models import (
    Queue,
    QueueTransitionLog,
    ServiceRequest,
    SurveyResponse,
    Visit,
    VisitDispatch,
    VisitTransitionLog,
)


class VisitTransitionLogSerializer(BaseSerializer):
    """VisitTransitionLog Serializer."""

    class Meta:
        """Serialization options."""

        model = VisitTransitionLog
        fields = "__all__"


class QueueTransitionSerializer(BaseSerializer):
    """QueueTransition Serializer."""

    source_queue_name = serializers.ReadOnlyField()
    destination_queue_name = serializers.ReadOnlyField()

    class Meta:
        """Serialization options."""

        model = QueueTransitionLog
        fields = "__all__"


class ServiceRequestSerializer(BaseSerializer):
    """Service Request Serializer."""

    queue_name = serializers.ReadOnlyField(source="queue.name")
    queue_type = serializers.ReadOnlyField(
        source="queue.queue_type",
    )
    invoice = InvoiceSerializer(read_only=True)
    patient_name = serializers.ReadOnlyField(
        source="visit.patient.person.get_full_name"
    )
    phone_number = serializers.SerializerMethodField()
    customer_id = serializers.ReadOnlyField(
        source="visit.patient.customer_id",
    )
    previous_point = serializers.ReadOnlyField(
        source="previous_queue_name",
    )
    clinical_order = ClinicalOrderSerializer(read_only=True)

    def get_phone_number(
        self,
        instance: ServiceRequest,
    ) -> Optional[str]:
        """Return the first phone number.

        This is being done here to avoid an extra trip to the DB for each
        person during list serialization.
        You MUST ensure that your viewsets prefetch the contacts
        otherwise we'll just be spinning wheels.
        """
        for contact in instance.visit.patient.person.person_contacts.all():
            if contact.contact_type == "phone_number":
                return contact.contact
        return None

    class Meta:
        """Serialization options."""

        model = ServiceRequest
        fields = "__all__"


class VisitDispatchSerializer(BaseSerializer):
    """Serializer for VisitDispatch model."""

    class Meta:
        """Serialization options."""

        model = VisitDispatch
        fields = ("status",)


class VisitSerializer(BaseSerializer):
    """Visit Serializer."""

    patient_name = serializers.ReadOnlyField(
        source="patient.person.get_full_name",
    )
    phone_number = serializers.SerializerMethodField()
    customer_id = serializers.ReadOnlyField(
        source="patient.customer_id",
    )
    service_requests = ServiceRequestSerializer(
        read_only=True,
        many=True,
        override_field_exclusion=True,
    )
    visit_dispatch = VisitDispatchSerializer(read_only=True)

    def get_phone_number(self, instance: Visit) -> Optional[str]:
        """Return the first phone number.

        This is being done here to avoid an extra trip to the DB for each
        person during list serialization.
        You MUST ensure that your viewsets prefetch the contacts
        otherwise we'll just be spinning wheels.
        """
        for contact in instance.patient.person.person_contacts.all():
            if contact.contact_type == "phone_number":
                return contact.contact
        return None

    class Meta:
        """Serialization options."""

        model = Visit
        fields = "__all__"


class QueueSerializer(BaseSerializer):
    """Queue Serializer."""

    active_visits: serializers.PrimaryKeyRelatedField = (
        serializers.PrimaryKeyRelatedField(
            read_only=True,
            many=True,
        )
    )

    class Meta:
        """Serialization options."""

        model = Queue
        fields = "__all__"


class SurveyResponseSerializer(BaseSerializer):
    """Survey Response Serializer."""

    class Meta:
        """Serialization options."""

        model = SurveyResponse
        fields = "__all__"
