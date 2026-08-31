"""Sample filters."""
import django_filters

from sil_advantage.common.filters import AllDateTimeFilter

from . import models


class ABCFilter(django_filters.FilterSet):
    """Sample filter."""

    from_date = AllDateTimeFilter(field_name="siku", lookup_expr="gte")
    to_date = AllDateTimeFilter(field_name="siku", lookup_expr="lte")

    class Meta:
        """Django filter options."""

        model = models.ABC
        fields = ["from_date", "to_date"]
