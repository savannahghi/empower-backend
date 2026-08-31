"""Shared serializer mixins."""
from typing import Any, Optional

from django.conf import settings
from django.core import exceptions
from django.db.models import Model
from django.utils.translation import gettext_lazy as _
from drf_writable_nested.serializers import WritableNestedModelSerializer
from rest_framework.serializers import (
    CharField,
    ModelSerializer,
    ValidationError,
)

from sil_advantage.common.models import Organisation
from sil_advantage.common.serializers.mixins import PartialResponseMixin
from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.permissions import perms as perms
from sil_advantage.sil_auth.models import SILUser


def get_organisation(
    request: AuthenticatedRequest,
    initial_data: Optional[dict | str] = None,
) -> Organisation:
    """Determine the organisation based on the user and supplied data."""
    user = request.user
    organisation = (
        initial_data.get("organisation")
        if isinstance(initial_data, dict)
        else request.data.get("organisation")
    )

    if user.is_anonymous or (
        organisation and user.has_permissions([perms.CROSS_NETWORK_ADMIN[0]])
    ):
        try:
            org = Organisation.objects.get(id=organisation)
        except Organisation.DoesNotExist:
            error = {"organisation": _("Ensure the organisation provided exists.")}
            raise exceptions.ValidationError(error)
        return org
    else:
        return user.organisation


class AuditFieldsMixin(PartialResponseMixin):
    """Mixin for organisation, created, updated, created_by and updated_by."""

    context: dict
    initial_data: dict

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the mixin by excluding the fields it manages."""
        override_field_exclusion = kwargs.pop(
            "override_field_exclusion",
            False,
        )
        kwargs.pop("override_field_exclusion", None)
        super().__init__(*args, **kwargs)
        exclude_fields = [
            "created",
            "created_by",
            "updated",
            "updated_by",
            "organisation",
            "cluster_id",
            "branch_id",
            "department_id",
            "workstation_id",
        ]
        context = getattr(self, "context", {})
        request = context.get("request", {})
        request_method = getattr(request, "method", "").upper()
        include_in_methods = ("GET", "HEAD", "OPTIONS")
        if request_method not in include_in_methods and not override_field_exclusion:
            for i in exclude_fields:
                if i in self.fields:  # type: ignore
                    self.fields.pop(i)  # type: ignore

    def _populate_audit_fields(
        self,
        data: dict,
        is_create: bool,
    ) -> dict:
        """Populate audit fields."""
        request = self.context["request"]
        user = request.user

        # Set network admin as the created_by and updated_by fields
        admin_email = settings.SYSTEM_ADMIN_EMAIL
        system_admin = SILUser.objects.get(email=admin_email).id

        if user.is_anonymous:
            data["updated_by"] = system_admin

        if not user.is_anonymous:
            data["updated_by"] = user.guid or user.pk

        if is_create:
            if user.is_anonymous:
                data["created_by"] = system_admin

            if not user.is_anonymous:
                data["created_by"] = user.guid or user.pk

            if hasattr(self.Meta.model, "cluster_id"):  # type: ignore
                data["cluster_id"] = request.META.get(
                    "HTTP_X_CLUSTER"
                ) or request.META.get("X-Cluster")
                data["branch_id"] = request.META.get(
                    "HTTP_X_BRANCH"
                ) or request.META.get("X-Branch")
                data["department_id"] = request.META.get(
                    "HTTP_X_DEPARTMENT"
                ) or request.META.get("X-Department")
                data["workstation_id"] = request.META.get(
                    "HTTP_X_WORKSTATION"
                ) or request.META.get("X-Workstation")

                if (
                    data["cluster_id"] is None
                    or data["branch_id"] is None
                    or data["department_id"] is None
                    or data["workstation_id"] is None
                ):
                    raise ValidationError(
                        _(
                            "Please provide the following headers: X-Cluster, "
                            "X-Branch, X-Department, & X-Workstation."
                        )
                    )

            # Do not do this for an Organisation serializer
            # or a model that does not have an organisation attribute
            has_organisation = hasattr(self.Meta.model, "organisation")  # type: ignore
            if self.Meta.model != Organisation and has_organisation:  # type: ignore
                # If an 'organisation' is not explicitly passed in,
                # use the logged in user's organisation, if the request if
                # for creation only
                data["organisation"] = get_organisation(
                    request,
                    self.initial_data,
                )
        return data

    def create(self, validated_data: dict):  # type: ignore
        """Ensure that ids are not supplied when creating new instances."""
        initial_data_id = isinstance(self.initial_data, dict) and self.initial_data.get(
            "id"
        )
        if initial_data_id or validated_data.get("id"):
            raise ValidationError(
                {"id": _("You are not allowed to pass object with an id")}
            )
        self._populate_audit_fields(validated_data, True)
        return super().create(validated_data)  # type: ignore

    def update(self, instance: Model, validated_data: dict):  # type: ignore
        """Ensure that audit fields are set when updating."""
        self._populate_audit_fields(validated_data, False)
        return super().update(instance, validated_data)  # type: ignore

    def get_fields(self) -> dict:
        """Implement support for responses that subset available fields."""
        origi_fields = super().get_fields()  # type: ignore
        request = self.context.get("request", None)
        return self.strip_fields(request, origi_fields)


class DynamicFieldsModelSerializerMixin:
    """A mixin  that controls which fields should be displayed.

    It takes an additional `model_fields` argument
    Ref: https://www.django-rest-framework.org/api-guide/serializers/#dynamically-modifying-fields # noqa: B950
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Override initialization."""
        model_fields = kwargs.pop("model_fields", None)

        super().__init__(*args, **kwargs)

        if model_fields is not None:
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(model_fields)
            existing = set(self.fields)  # type: ignore
            for field_name in existing - allowed:
                self.fields.pop(field_name)  # type: ignore


class BaseSerializer(AuditFieldsMixin, ModelSerializer):
    """Base class intended for inheritance by 'regular' app serializers."""

    created_by_name = CharField(read_only=True)
    updated_by_name = CharField(read_only=True)


class WritabledNestedBaseSerializer(
    AuditFieldsMixin,
    WritableNestedModelSerializer,
):
    """Writable Nested Base Serializer."""

    pass
