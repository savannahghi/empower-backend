"""Segments filters."""
from django_filters import rest_framework as filters

from sil_advantage.common.filters.base import CommonFieldsFilterset
from sil_advantage.segments.models import (
    Journey,
    JourneyAttributes,
    JourneyMember,
    JourneySegment,
    MessageTemplate,
    MessageTemplateTransitionLog,
    Segment,
    SegmentMember,
    SegmentMemberTransitionLog,
    SegmentMessage,
    SegmentMessageDelivery,
    SegmentUpload,
)
from sil_advantage.segments.models.filters import FilterGroup, FilterGroupFilter
from sil_advantage.segments.models.segments import SegmentTransitionLog


class SegmentFilter(CommonFieldsFilterset):
    """Segment filter."""

    class Meta:
        """Filter options."""

        model = Segment
        exclude = ["attributes"]


class SegmentMessageFilter(CommonFieldsFilterset):
    """SegmentMessage filter."""

    class Meta:
        """Filter options."""

        model = SegmentMessage
        fields = "__all__"


class SegmentMemberFilter(CommonFieldsFilterset):
    """SegmentMember filter."""

    class Meta:
        """Filter options."""

        model = SegmentMember
        exclude = ["extra_data"]


class MessageTemplateFilter(CommonFieldsFilterset):
    """MessageTemplate filter."""

    class Meta:
        """Filter options."""

        model = MessageTemplate
        fields = "__all__"


class SegmentMessageDeliveryFilter(CommonFieldsFilterset):
    """Segment Message Delivery filter."""

    segment_message_id = filters.UUIDFilter(field_name="segment_message")
    message_id = filters.UUIDFilter(field_name="message_template")
    state = filters.CharFilter(field_name="sms__state")

    class Meta:
        """Filter options."""

        model = SegmentMessageDelivery
        fields = "__all__"


class SegmentUploadFilter(CommonFieldsFilterset):
    """SegmentUpload filter."""

    process_state = filters.CharFilter(field_name="file_upload__process_state")

    class Meta:
        """Filter options."""

        model = SegmentUpload
        fields = ["segment", "process_state"]


class SegmentTransitionLogFilter(CommonFieldsFilterset):
    """SegmentTransitionLog filter."""

    class Meta:
        """Filter options."""

        model = SegmentTransitionLog
        fields = "__all__"


class MessageTemplateTransitionLogFilter(CommonFieldsFilterset):
    """MessageTemplateTransitionLog filter."""

    class Meta:
        """Filter options."""

        model = MessageTemplateTransitionLog
        fields = "__all__"


class SegmentMemberTransitionLogFilter(CommonFieldsFilterset):
    """SegmentMemberTransitionLog filter."""

    class Meta:
        """Filter options."""

        model = SegmentMemberTransitionLog
        fields = "__all__"


class FilterGroupFilterset(CommonFieldsFilterset):
    """FilterGroup filter."""

    class Meta:
        """Filter options."""

        model = FilterGroup
        fields = "__all__"


class FilterGroupFilterFilter(CommonFieldsFilterset):
    """FilterGroupFilter filter."""

    class Meta:
        """Filter options."""

        model = FilterGroupFilter
        fields = "__all__"


class JourneyFilter(CommonFieldsFilterset):
    """Journey filter."""

    class Meta:
        """Serializer options."""

        model = Journey
        fields = "__all__"


class JourneySegmentFilter(CommonFieldsFilterset):
    """JourneySegment filter."""

    class Meta:
        """Serializer options."""

        model = JourneySegment
        fields = "__all__"


class JourneyMemberFilter(CommonFieldsFilterset):
    """JourneyMember filter."""

    class Meta:
        """Serializer options."""

        model = JourneyMember
        fields = "__all__"


class JourneyAttributeFilter(CommonFieldsFilterset):
    """JourneyAttribute filter."""

    class Meta:
        """Serializer options."""

        model = JourneyAttributes
        fields = "__all__"
