"""SMS filters."""
from django.contrib.postgres.fields import ArrayField
from django_filters import rest_framework as filters

from sil_advantage.common.filters.base import CommonFieldsFilterset
from sil_advantage.common.filters.common_filters import AllDateTimeFilter
from sil_advantage.notifications.sms.models import SMS, SenderID


class SenderIDFilter(CommonFieldsFilterset):
    """SenderID filter."""

    class Meta:
        """Filter options."""

        model = SenderID
        fields = "__all__"


class SMSFilter(CommonFieldsFilterset):
    """SMS filter."""

    date_to = AllDateTimeFilter(field_name="created", lookup_expr="lte")
    date_from = AllDateTimeFilter(field_name="created", lookup_expr="gte")

    class Meta:
        """Filter options."""

        model = SMS
        fields = "__all__"
        filter_overrides = {
            ArrayField: {
                "filter_class": filters.CharFilter,
                "extra": lambda f: {
                    "lookup_expr": "icontains",
                },
            },
        }
