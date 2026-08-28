"""Filters Serializer."""
from rest_framework import serializers

from sil_advantage.common.serializers import (
    BaseSerializer,
    DynamicFieldsModelSerializerMixin,
)
from sil_advantage.segments.models import Filter, FilterGroup, FilterGroupFilter


class FilterSerializer(BaseSerializer):
    """Serializer for the Filter model."""

    class Meta:
        """Serializer options."""

        model = Filter
        fields = "__all__"


class FilterGroupFilterSerializer(DynamicFieldsModelSerializerMixin, BaseSerializer):
    """Serializer for the FilterGroupFilter model."""

    filter = FilterSerializer(read_only=True)

    filter_id = serializers.UUIDField(write_only=True)

    class Meta:
        """Serializer options."""

        model = FilterGroupFilter
        fields = "__all__"


class FilterGroupSerializer(DynamicFieldsModelSerializerMixin, BaseSerializer):
    """Serializer for the FilterGroup model."""

    filters = FilterGroupFilterSerializer(
        model_fields=["id", "filter", "operation", "value"], many=True, read_only=True
    )

    class Meta:
        """Serializer options."""

        model = FilterGroup
        fields = "__all__"


class FilterChoicesSerializer(serializers.Serializer):
    """Serializer for filter choices."""

    name = serializers.CharField()
    value = serializers.CharField()
