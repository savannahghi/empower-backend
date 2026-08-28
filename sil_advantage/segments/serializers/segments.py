"""Segments serializers."""
from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from sil_advantage.common.serializers import (
    BaseSerializer,
    DynamicFieldsModelSerializerMixin,
    PersonSerializer,
)
from sil_advantage.notifications.sms.serializers import SMSSerializer
from sil_advantage.patients.serializers import PatientListUploadSerializer
from sil_advantage.segments.models import (
    Segment,
    SegmentMember,
    SegmentMemberTransitionLog,
    SegmentMessageDelivery,
    SegmentTransitionLog,
    SegmentUpload,
)
from sil_advantage.segments.tasks import execute_segment_filter_cube_query

from .filters import FilterGroupFilterSerializer, FilterGroupSerializer
from .templates import MessageTemplateSerializer


class FilterInputSerializer(serializers.Serializer):
    """Filter Input Serializer."""

    filter_id = serializers.UUIDField()
    operation = serializers.CharField()
    value = serializers.CharField()


class FilterGroupInputSerializer(serializers.Serializer):
    """Filter Group Input Serializer."""

    name = serializers.CharField()
    filters = FilterInputSerializer(many=True, required=True)


class SegmentSerializer(DynamicFieldsModelSerializerMixin, BaseSerializer):
    """Segment Serializer."""

    welcome_message_template = MessageTemplateSerializer(read_only=True)

    welcome_message_template_id = serializers.UUIDField(write_only=True, required=False)
    filter_groups = FilterGroupInputSerializer(
        many=True, write_only=True, required=False
    )

    class Meta:
        """Serializer options."""

        model = Segment
        fields = [
            "id",
            "name",
            "label",
            "description",
            "attributes",
            "ussd_enabled",
            "status",
            "created",
            "member_count",
            "welcome_message_template",
            "welcome_message_template_id",
            "send_welcome_message_notification",
            "filter_execution_status",
            "filter_groups",
        ]
        read_only_fields = ["status"]

    @transaction.atomic
    def create(self, validated_data: dict) -> Segment:
        """Create filter groups and filters."""
        filter_groups_input = validated_data.pop("filter_groups", None)

        segment = super().create(validated_data)
        if not filter_groups_input:
            return segment

        for filter_group_input in filter_groups_input:
            fg_data = {
                "name": filter_group_input.get("name"),
                "segment": segment.id,
            }

            fg_serializer = FilterGroupSerializer(
                data=fg_data, context={"request": self.context["request"]}
            )
            fg_serializer.is_valid(raise_exception=True)
            filter_group = fg_serializer.save()

            filter_group_filters = []
            for filter_input in filter_group_input.get("filters"):
                f_data = {
                    "filter_group": filter_group.id,
                    "filter_id": filter_input.get("filter_id"),
                    "operation": filter_input.get("operation"),
                    "value": filter_input.get("value"),
                }

                filter_group_filters.append(f_data)

            fgf_serializer = FilterGroupFilterSerializer(
                data=filter_group_filters,
                many=True,
                context={"request": self.context["request"]},
            )
            fgf_serializer.is_valid(raise_exception=True)
            fgf_serializer.save()

        execute_segment_filter_cube_query.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_HIGH_PRIORITY,
            args=(str(segment.id),),
        )

        return segment


class SegmentMemberInputSerializer(serializers.Serializer):
    """Serialize SegmentMember input."""

    clinical_id = serializers.CharField()
    segment_label = serializers.CharField()


class SegmentMemberSerializer(BaseSerializer):
    """Segment Member Serializer."""

    segment = SegmentSerializer(model_fields=["id", "name"], read_only=True)
    person = PersonSerializer(read_only=True)

    segment_id = serializers.UUIDField(write_only=True)
    person_id = serializers.UUIDField(write_only=True)
    consent_status = serializers.CharField(
        source="person.sms_consent_status", read_only=True
    )
    status = serializers.CharField(read_only=True)

    class Meta:
        """Serializer options."""

        model = SegmentMember
        fields = "__all__"


class SegmentUploadSerializer(BaseSerializer):
    """Segment Upload Serializer."""

    file_upload = PatientListUploadSerializer(read_only=True)

    class Meta:
        """Serializer options."""

        model = SegmentUpload
        fields = "__all__"


class SegmentMessageDeliverySerializer(BaseSerializer):
    """Segment Message Delivery Serializer."""

    sms = SMSSerializer(read_only=True)
    member = SegmentMemberSerializer(read_only=True)

    class Meta:
        """Serializer options."""

        model = SegmentMessageDelivery
        fields = "__all__"


class SegmentTransitionLogSerializer(BaseSerializer):
    """Serialize segment transition."""

    class Meta:
        """Define serialization options."""

        model = SegmentTransitionLog
        fields = "__all__"


class SegmentMemberTransitionLogSerializer(BaseSerializer):
    """Serialize segment member transition."""

    class Meta:
        """Define serialization options."""

        model = SegmentMemberTransitionLog
        fields = "__all__"
