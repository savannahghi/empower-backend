"""Template serializer."""
from typing import Any, Dict

from django.conf import settings
from rest_framework import serializers

from sil_advantage.common.serializers import BaseSerializer
from sil_advantage.notifications.sms.serializers import SenderIDSerializer
from sil_advantage.segments.models import (
    MessageTemplate,
    MessageTemplateTransitionLog,
    SegmentMember,
    SegmentMessage,
    SegmentMessageDeliveryType,
)


def template_translation_fields() -> list[str]:
    """Dynamically return translated fields."""
    fields = []

    for language, _ in settings.LANGUAGES:
        fields.append(f"template_{language}")

    return fields


class MessageTemplateSerializer(BaseSerializer):
    """MessageTemplate Serializer."""

    sequence = serializers.CharField(
        read_only=True, required=False, source="tree_depth"
    )
    has_sequence = serializers.BooleanField(read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        """Serializer options."""

        model = MessageTemplate
        fields = [
            "id",
            "name",
            "parent",
            "template",
            "message_type",
            "status",
            "sequence",
            "has_sequence",
            "created",
        ] + template_translation_fields()

    def to_representation(self, instance: MessageTemplate) -> dict:
        """Provide a "humanised" sequence number.

        The sequence counter for sequenced messages starts from 0,
        which is not intuitive for the users of the system.
        This increments the sequence by 1 to make it make sense.
        """
        data = super().to_representation(instance)

        if data.get("sequence"):
            sequence = int(data["sequence"]) + 1
            data["sequence"] = str(sequence)

        return data

    def create(self, validated_data: dict):  # type: ignore
        """Modifies the template translation option."""
        request = self.context["request"]
        # translation option for the current language is set automatically
        validated_data.pop(f"template_{request.LANGUAGE_CODE}", None)
        return super().create(validated_data)


class SegmentMessageSerializer(BaseSerializer):
    """Segment Message Serializer."""

    sender = SenderIDSerializer(required=False, read_only=True)
    message = MessageTemplateSerializer(read_only=True, source="template")
    sender_id = serializers.UUIDField(required=False, write_only=True)

    class Meta:
        """Serializer options."""

        model = SegmentMessage
        fields = "__all__"


class SegmentSMSSerializer(serializers.Serializer):
    """Segment SMS Serializer."""

    template_id = serializers.UUIDField(required=False)
    template = serializers.CharField(required=False)
    sender_id = serializers.UUIDField(required=False)
    segment_ids = serializers.ListField(child=serializers.UUIDField())
    scheduled_at = serializers.DateTimeField(required=False)
    delivery_type = serializers.CharField()
    sequence_interval = serializers.CharField(required=False)
    send_on_segment_join = serializers.BooleanField(required=True)

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate field values before saving."""
        # XOR operation
        template_id_and_template_obj_keys_exists = ("template_id" in data) ^ (
            "template" in data
        )

        if not template_id_and_template_obj_keys_exists:
            raise serializers.ValidationError(
                "Either Template ID or Template Object should be provided!"
            )

        if (
            data["delivery_type"] == SegmentMessageDeliveryType.SCHEDULED_ONE_TIME
            and data.get("scheduled_at") is None
        ):
            raise serializers.ValidationError(
                "Schedule should be provided for a scheduled message!"
            )
        elif (
            data["delivery_type"] == SegmentMessageDeliveryType.SCHEDULED_RECURRENT
            and data.get("sequence_interval") is None
        ):
            raise serializers.ValidationError(
                "Interval should be provided for a scheduled recurrent message!"
            )

        recipients = SegmentMember.objects.filter(
            segment_id__in=data["segment_ids"]
        ).exists()

        if not recipients:
            raise serializers.ValidationError(
                "Segment(s) provided has no active members!"
            )

        return data


class MessageTemplateTransitionLogSerializer(BaseSerializer):
    """Serialize MessageTemplate transitions."""

    class Meta:
        """Define serialization options."""

        model = MessageTemplateTransitionLog
        fields = "__all__"
