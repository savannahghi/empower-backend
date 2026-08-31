"""Shared view base classes and mixins."""
import logging
from typing import Any, Optional, cast

from django.db.models.query import QuerySet
from django.utils.functional import cached_property
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import (
    ListSerializer,
    ModelSerializer,
    SerializerMethodField,
)
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.viewsets import ModelViewSet
from sil_cacheable.views import CacheableViewMixin
from sil_transitions import TransitionViewMixin

from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.sil_auth.permission_classes import (
    OrganisationIsActive,
    ViewBasePermission,
)

LOGGER = logging.getLogger(__name__)


class BaseView(ModelViewSet):
    """Base class for most application views.

    This view's `create` method has been extended to support
    the creation of a single or multiple records.
    """

    permission_classes: tuple = (
        IsAuthenticated & ViewBasePermission & OrganisationIsActive,
    )

    permissions: dict[str, list] = {
        "GET": [],
        "POST": [],
        "PATCH": [],
        "DELETE": [],
    }
    scopes: dict[str, list] = {
        "GET": [],
        "POST": [],
        "PATCH": [],
        "DELETE": [],
    }

    _select_related: list[str] = []
    _prefetch_related: list[str] = []

    _data_partition_field: Optional[str] = "branch_id"

    def get_queryset(self) -> QuerySet:
        """Return an optimized queryset based on ?fields=.

        Based on the requested fields from the frontend,
        this helps reduce the number of trips to the DB by
        automatically prefetching and selecting as required.
        These trips can be in the hundreds on /list endpoints.
        It also reduces the number of JOINs if we don't need that data.

        Some access paths for this function are O(n^3) :(
        but it's worth the effort since we save extra trips to
        the DB downstream.
        """
        filtered_select = set(self._select_related)
        filtered_prefetch = set(self._prefetch_related)

        fields_param = self.request.query_params.get("fields", None)
        if fields_param is not None:
            filtered_select, filtered_prefetch = set(), set()
            serializer = cast(ModelSerializer, self.get_serializer())
            fields = serializer.get_fields()
            for name, field in fields.items():
                if (
                    field.source is None
                    and not isinstance(
                        field,
                        (ModelSerializer, ListSerializer),
                    )
                ) or isinstance(field, SerializerMethodField):
                    # This field is an attribute of the current model
                    # or a SerializerMethodField.
                    # Stay away from SerializerMethodField if you
                    # can since we can't introspect it :(.
                    continue

                traversal = (cast(str, field.source) or name).split(".")
                for i in range(len(traversal)):
                    source = "__".join(traversal[: i + 1])
                    filtered_select.update(
                        select
                        for select in self._select_related
                        if select.startswith(source)
                    )
                    filtered_prefetch.update(
                        prefetch
                        for prefetch in self._prefetch_related
                        if prefetch.startswith(source)
                    )

        qs = super().get_queryset()
        if len(filtered_select) > 0:
            qs = qs.select_related(*filtered_select)
        if len(filtered_prefetch) > 0:
            qs = qs.prefetch_related(*filtered_prefetch)
        return qs

    def create(
        self, request: AuthenticatedRequest, *args: Any, **kwargs: Any
    ) -> Response:
        """Create and persist single or multiple records."""
        # Check if the data given by the user is composed of a single or
        # multiple records.
        has_many = isinstance(request.data, list)

        # Initialize this viewset's serializer to handle multiple or a single
        # records depending on the value of `has_many` and proceed to create
        # the data.
        serializer = self.get_serializer(data=request.data, many=has_many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class CacheableBaseView(CacheableViewMixin, BaseView):
    """Cacheable Base View."""

    request: AuthenticatedRequest

    @cached_property
    def _bp_id(self) -> str:
        """Get the user organisation."""
        branch_id = str(
            self.request.META.get("HTTP_X_BRANCH") or self.request.META.get("X-Branch")
        )
        organisation_id = str(self.request.user.organisation.id)
        queryset = self.get_queryset()

        if hasattr(queryset.model, "branch_id"):
            return f"{organisation_id}.{branch_id}"
        else:
            return organisation_id


class OrganisationTransitionMixin(TransitionViewMixin):
    """This handles creation of organisation transition logs at the view."""

    def get_transition(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> str | bool:
        """Override the default since we are working with boolean fields."""
        val = kwargs.pop(self.transition_field, "").capitalize()

        if val == "True":
            return True
        elif val == "False":
            return False
        return val


class LenientAnonThrottle(ScopedRateThrottle):
    """This applies lenient throttling on open endpoints.

    This endpoints include the survey form endpoint.
    """

    scope = "lenient_anon"
