"""Visits filters."""
from sil_advantage.common.filters.base import CommonFieldsFilterset, ListFilter
from sil_advantage.visits.models import (
    Queue,
    ServiceRequest,
    SurveyResponse,
    Visit,
)


class VisitFilter(CommonFieldsFilterset):
    """Visit filter."""

    status = ListFilter()
    visit_type = ListFilter()
    priority = ListFilter()
    billing_class = ListFilter()

    class Meta:
        """Filter options."""

        model = Visit
        fields = "__all__"


class QueueFilter(CommonFieldsFilterset):
    """Queue filter."""

    queue_type = ListFilter()
    schedule_actor = ListFilter(
        field_name="schedule__actor",
        lookup_expr="in",
    )

    class Meta:
        """Filter options."""

        model = Queue
        fields = "__all__"


class ServiceRequestFilter(CommonFieldsFilterset):
    """Service Request filter."""

    status = ListFilter()
    priority = ListFilter()

    class Meta:
        """Filter options."""

        model = ServiceRequest
        fields = "__all__"


class SurveyResponseFilter(CommonFieldsFilterset):
    """Survey Response filter."""

    class Meta:
        """Filter options."""

        model = SurveyResponse
        exclude = ("response",)
