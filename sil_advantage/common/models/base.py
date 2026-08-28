"""Abstract base models and mixins used by the entire system."""
import logging
import uuid
from typing import Any, Sequence

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from sil_advantage.common.models.mixins import (
    ValidationErrorsMixin,
    ValidationMetaclass,
)
from sil_advantage.common.models.organisation_models import Organisation

LOGGER = logging.getLogger(__file__)


class OwnerlessAbstractBase(
    ValidationErrorsMixin, models.Model, metaclass=ValidationMetaclass
):
    """Base class for models that are not linked to an organisation."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.UUIDField(editable=False)
    updated = models.DateTimeField(auto_now=True)
    updated_by = models.UUIDField()

    model_validators: Sequence[str] = []

    def preserve_created_and_created_by(self) -> None:
        """Ensure that in created and created_by fields are not overwritten."""
        try:
            model_class = self.__class__
            original = model_class.objects.get(pk=self.pk)
            self.created = original.created
            self.created_by = original.created_by
        except model_class.DoesNotExist:
            pass

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Handle audit fields correctly when saving."""
        self.preserve_created_and_created_by()
        super().save(*args, **kwargs)

    class Meta:
        """Define a sensible default ordering."""

        abstract = True
        ordering: tuple[str, ...] = ("-updated", "-created")


class AbstractBase(OwnerlessAbstractBase):
    """Base class for most models in the application."""

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_related",
    )

    organisation_verify: Sequence[str] = []
    model_validators: Sequence[str] = [
        "validate_organisation",
    ]

    @cached_property
    def owner(self) -> int:
        """Return the record's owner."""
        return self.organisation.slade_code

    @cached_property
    def _bp_id(self) -> str:
        """Return the model's BP ID."""
        if hasattr(self, "branch_id"):
            return f"{str(self.organisation_id)}.{str(self.branch_id)}"
        else:
            return str(self.organisation_id)

    @cached_property
    def created_by_name(self) -> str | None:
        """Returns the name of the user who created the record."""
        try:
            user = get_user_model().objects.get(guid=self.created_by)
            return user.get_full_name()
        except get_user_model().DoesNotExist:
            return None

    @cached_property
    def updated_by_name(self) -> str | None:
        """Returns the name of the user who updated the record."""
        try:
            user = get_user_model().objects.get(guid=self.updated_by)
            return user.get_full_name()
        except get_user_model().DoesNotExist:
            return None

    def validate_organisation(self) -> None:
        """Verify that orgs in FKs are consistent with those being created."""
        error_msg = _(
            " ".join(
                [
                    "The organisation provided is not consistent",
                    "with that of organisation fields in",
                    "related resources",
                ]
            )
        )
        if self.organisation_verify:
            for field in self.organisation_verify:
                value = getattr(self, field)
                if value:
                    if str(self.organisation_id) != str(value.organisation_id):
                        LOGGER.error(f"{field} has an inconsistent org")
                        raise ValidationError({"organisation": _(str(error_msg))})

    class Meta(OwnerlessAbstractBase.Meta):
        """Define a sensible default ordering."""

        abstract = True
