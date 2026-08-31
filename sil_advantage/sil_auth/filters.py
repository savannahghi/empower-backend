"""User filters."""
from uuid import UUID

import django_filters
from django.db.models import QuerySet

from sil_advantage.common.filters.base import CommonFieldsFilterset
from sil_advantage.common.models import Organisation, UserProfile
from sil_advantage.sil_auth import models


class SILUserFilter(CommonFieldsFilterset):
    """Users filter."""

    organisation = django_filters.UUIDFilter(
        method="filter_by_organisation",
    )

    def filter_by_organisation(
        self,
        queryset: QuerySet[models.SILUser],
        field: str,
        value: UUID,
    ) -> QuerySet[models.SILUser]:
        """Return only users from to the organisation with the given PK."""
        organisation = Organisation.objects.get(pk=value)
        organisation_user_profiles = UserProfile.objects.filter(
            organisation=organisation
        )
        organisation_user_pks = organisation_user_profiles.values_list(
            "user__pk", flat=True
        )
        return queryset.filter(pk__in=organisation_user_pks)

    class Meta:
        """User filter options."""

        model = models.SILUser
        fields = "__all__"


class UserMFAFilter(CommonFieldsFilterset):
    """User MFA filter."""

    class Meta:
        """User MFA filter options."""

        model = models.SILUserMFA
        fields = "__all__"
