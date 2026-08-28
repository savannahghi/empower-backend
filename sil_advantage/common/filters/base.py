"""Base filters."""
from typing import Any

import django_filters
from django.db.models import QuerySet
from rest_framework.filters import SearchFilter


class ListFilter(django_filters.BaseInFilter, django_filters.CharFilter):
    """Base filter for classes that need to take lists e.g workflow states."""

    pass


class CommonFieldsFilterset(django_filters.FilterSet):
    """This is intended to be the base filter for most app filtersets."""

    search = SearchFilter()

    def inactive_records(
        self,
        queryset: QuerySet,
        field: str,
        value: Any,
    ) -> QuerySet:
        """Select *inactive* records only.

        This function allows filtering of only the fields with active=False
        To display the inactive records the query param should be set to
        active=False or an equivalence as specified below
        """
        return queryset.filter(active=value)

    active = django_filters.BooleanFilter(method="inactive_records")
