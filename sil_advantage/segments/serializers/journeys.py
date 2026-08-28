"""Journey Serializer."""
from django.db import transaction

from sil_advantage.common.serializers import BaseSerializer
from sil_advantage.segments.models import (
    Journey,
    JourneyAttributes,
    JourneyMember,
    JourneySegment,
)
from sil_advantage.segments.serializers.segments import FilterInputSerializer


class JourneySerializer(BaseSerializer):
    """Journey serializer."""

    journey_attributes = FilterInputSerializer(
        many=True, write_only=True, required=False
    )

    class Meta:
        """Serializer options."""

        model = Journey
        fields = [
            "name",
            "description",
            "journey_attributes",
        ]

    @transaction.atomic
    def create(self, validated_data: dict):  # type: ignore
        """Create journey and journey attributes."""
        journey_attributes_input = validated_data.pop("journey_attributes", None)

        journey = super().create(validated_data)
        if not journey_attributes_input:
            return journey

        journey_attributes = []
        for journey_attribute_input in journey_attributes_input:
            attribute_data = {
                "journey": journey.id,
                "filter": journey_attribute_input.get("filter_id"),
                "operation": journey_attribute_input.get("operation"),
                "value": journey_attribute_input.get("value"),
            }

            journey_attributes.append(attribute_data)

        journey_attributes_serializer = JourneyAttributeSerializer(
            data=journey_attributes,
            many=True,
            context={"request": self.context["request"]},
        )
        journey_attributes_serializer.is_valid(raise_exception=True)
        journey_attributes_serializer.save()

        return journey


class JourneySegmentSerializer(BaseSerializer):
    """JourneySegment serializer."""

    class Meta:
        """Serializer options."""

        model = JourneySegment
        fields = "__all__"


class JourneyMemberSerializer(BaseSerializer):
    """JourneyMember serializer."""

    class Meta:
        """Serializer options."""

        model = JourneyMember
        fields = "__all__"


class JourneyAttributeSerializer(BaseSerializer):
    """JourneyAttribute serializer."""

    class Meta:
        """Serializer options."""

        model = JourneyAttributes
        fields = "__all__"
