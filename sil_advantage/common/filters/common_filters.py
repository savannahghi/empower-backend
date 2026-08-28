"""Filters for common models."""
from django.conf import settings
from django.db.models import QuerySet, TextField
from django.db.models.functions import Cast
from django_filters import CharFilter, FilterSet
from django_filters.fields import IsoDateTimeField
from django_filters.filters import IsoDateTimeFilter
from phonenumber_field.modelfields import PhoneNumberField
from rest_framework import filters

from sil_advantage.common import models
from sil_advantage.common.filters.base import CommonFieldsFilterset, ListFilter
from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.permissions import perms


class OrgUnitFilterBackend(filters.BaseFilterBackend):
    """Filter results by organisation and org units."""

    def filter_queryset(  # type: ignore  # import cycle issue
        self,
        request: AuthenticatedRequest,
        queryset: QuerySet,
        view,
    ) -> QuerySet:
        """Filter results by organisation and org units."""
        data_partition_field = getattr(
            view,
            "_data_partition_field",
            None,
        )
        if data_partition_field is None:
            return queryset

        user = request.user
        filters = {"organisation": user.organisation}

        user_agent = request.META.get("User-Agent") or request.META.get(
            "HTTP_USER_AGENT"
        )

        # Cross-network admins should see everything in all organisations
        is_cross_network_admin = user.has_permissions([perms.CROSS_NETWORK_ADMIN[0]])
        if user_agent in settings.API_USER_AGENTS and is_cross_network_admin:
            return queryset

        # Org-level admins should see everything in their organisation
        is_org_admin = user.has_permissions([perms.ORGANISATION_ADMIN[0]])
        if is_org_admin:
            return queryset.filter(**filters)

        # Cluster Admins should see everything on their cluster
        is_cluster_admin = user.has_permissions([perms.CLUSTER_ADMIN[0]])
        if hasattr(queryset.model, "cluster_id") and is_cluster_admin:
            cluster_id = request.META.get("HTTP_X_CLUSTER") or request.META.get(
                "X-Cluster"
            )
            filters["cluster_id"] = cluster_id
            return queryset.filter(**filters)
        is_branch_admin = user.has_permissions([perms.BRANCH_ADMIN[0]])
        if hasattr(queryset.model, "branch_id") and is_branch_admin:
            # Branch Admins should see everything on their branch
            branch_id = request.META.get("HTTP_X_BRANCH") or request.META.get(
                "X-Branch"
            )
            filters["branch_id"] = branch_id
            return queryset.filter(**filters)

        if hasattr(queryset.model, "department_id"):
            # Normal users
            filters["department_id"] = request.META.get(
                "HTTP_X_DEPARTMENT"
            ) or request.META.get("X-Department")
            if data_partition_field == "department_id":
                return queryset.filter(**filters)

        if hasattr(queryset.model, "workstation_id"):
            filters["workstation_id"] = request.META.get(
                "HTTP_X_WORKSTATION"
            ) or request.META.get("X-Workstation")

        return queryset.filter(**filters)


class OrganisationFilter(FilterSet):
    """Filter organisations."""

    search = filters.SearchFilter()

    class Meta:
        """Set up organisation filter, including phone number handling."""

        model = models.Organisation
        fields = "__all__"
        filter_overrides = {
            PhoneNumberField: {
                "filter_class": CharFilter,
                "extra": lambda f: {"lookup_expr": "icontains"},
            }
        }


class PersonFilter(CommonFieldsFilterset):
    """Filter persons."""

    class Meta:
        """Set up filter options."""

        model = models.Person
        exclude = ("metadata",)


class RelatedPersonFilter(CommonFieldsFilterset):
    """Filter related persons."""

    relationship = ListFilter()

    class Meta:
        """Set filter options."""

        model = models.RelatedPerson
        fields = "__all__"


class PersonIDFilter(CommonFieldsFilterset):
    """Filter person IDs."""

    first_name = CharFilter(
        field_name="person__first_name",
        lookup_expr="icontains",
    )
    last_name = CharFilter(
        field_name="person__last_name",
        lookup_expr="icontains",
    )

    class Meta:
        """Set up filter options."""

        model = models.PersonID
        fields = "__all__"


class PersonContactFilter(CommonFieldsFilterset):
    """Filter person contacts."""

    class Meta:
        """Set up filter options."""

        model = models.PersonContact
        fields = "__all__"


class PersonAttachmentFilter(CommonFieldsFilterset):
    """Filter person attachments."""

    class Meta:
        """Set up filter options."""

        model = models.PersonAttachment
        exclude = (
            "data",
            "metadata",
        )


class UserProfileFilter(CommonFieldsFilterset):
    """Filter user profiles."""

    first_name = CharFilter(
        field_name="person__first_name",
        lookup_expr="icontains",
    )
    last_name = CharFilter(
        field_name="person__last_name",
        lookup_expr="icontains",
    )
    organisation_name = CharFilter(
        field_name="organisation__organisation_name",
        lookup_expr="icontains",
    )

    class Meta:
        """Set up filter options."""

        model = models.UserProfile
        fields = "__all__"


class AllDateTimeField(IsoDateTimeField):
    """Extend django-filters to filter `ISO 8601` datetime formats.

    django_filters's `IsoDateTimeField` only supports `ISO 8601`
    and django's `DateTimeField` does not support `ISO 8601`.
    """

    # supported datetime formats
    input_formats = [IsoDateTimeField.ISO_8601] + [
        # year, month, day
        "%Y-%m-%d %H:%M:%S",  # '2006-10-25 14:30:59'
        "%Y-%m-%d %H:%M",  # '2006-10-25 14:30'
        "%Y-%m-%d",  # '2006-10-25'
        "%Y/%m/%d %H:%M:%S",  # '2006/10/25 14:30:59'
        "%Y/%m/%d %H:%M",  # '2006/10/25 14:30'
        "%Y/%m/%d",  # '2006/10/25'
        # day, month, year
        "%d-%m-%Y %H:%M:%S",  # '25-10-2006 14:30:59'
        "%d-%m-%Y %H:%M",  # '25-10-2006 14:30'
        "%d-%m-%Y",  # '25-10-2006'
        "%d/%m/%Y %H:%M:%S",  # '25/10/2006 14:30:59'
        "%d/%m/%Y %H:%M",  # '25/10/2006 14:30'
        "%d/%m/%Y",  # '25/10/2006'
    ]


class AllDateTimeFilter(IsoDateTimeFilter):
    """Custom date time filter."""

    field_class = AllDateTimeField


class Practitionerfilter(CommonFieldsFilterset):
    """Filter practitioners."""

    class Meta:
        """Setup filter options."""

        model = models.Practitioner
        fields = "__all__"


class OrganisationOnboardingfilter(CommonFieldsFilterset):
    """Organisation onboarding filters."""

    class Meta:
        """Filter options."""

        model = models.OrganisationOnboarding
        fields = "__all__"
        exclude = ["preferences"]


class ConsentFilter(CommonFieldsFilterset):
    """Filter for consents."""

    class Meta:
        """Setup filter options."""

        model = models.Consent
        fields = "__all__"


class OperatingRegionFilter(CommonFieldsFilterset):
    """Filter for operating regions, including heirachy_structure."""

    heirachy_structure = CharFilter(method="filter_heirachy_structure")

    class Meta:
        """Setup filter options."""

        model = models.OperatingRegion
        fields = "__all__"

    def filter_heirachy_structure(
        self, queryset: QuerySet, name: str, value: str
    ) -> QuerySet:
        """Custom filter method to search within the heirachy_structure JSON field."""
        return queryset.annotate(
            heirachy_text=Cast("heirachy_structure", TextField())
        ).filter(heirachy_text__icontains=value)


class BranchFilterBackend(filters.BaseFilterBackend):
    """Filter results by user branch."""

    def filter_queryset(  # type: ignore
        self, request: AuthenticatedRequest, queryset: QuerySet, view
    ) -> QuerySet:
        """Filter results by user branch."""
        user = request.user
        filters = {"organisation": user.organisation}

        branch_id = request.META.get("HTTP_X_BRANCH") or request.headers.get("X-Branch")

        if branch_id:
            filters["branch_id"] = branch_id

        return queryset.filter(**filters)
