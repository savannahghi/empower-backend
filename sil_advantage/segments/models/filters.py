"""Segment filters models."""
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from jsonschema import ValidationError as JSONSchemaValidationError
from jsonschema import validate

from sil_advantage.common.models import (
    AbstractBase,
    OrgUnitIdsMixin,
    OwnerlessAbstractBase,
)

CLOSE_ENDED_CHOICES_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Close-ended choices schema",
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
    },
}


def validate_close_ended_choices(value: dict) -> None:
    """Validates that the provided attributes for a schema are valid."""
    try:
        validate(instance=value, schema=CLOSE_ENDED_CHOICES_SCHEMA)
    except JSONSchemaValidationError as e:
        raise ValidationError(message=e.message)


class FilterExecutionStatus(models.TextChoices):
    """Tracks the status of executing the selected filter criteria for a segment."""

    PENDING = "PENDING", _("Pending")
    IN_PROGRESS = "IN_PROGRESS", _("In Progress")
    FAILED = "FAILED", _("Failed")
    SUCCESS = "SUCCESS", _("Success")


class FilterSource(models.TextChoices):
    """Indicates where the data of the filter is located."""

    CLINICAL = "CLINICAL", _("Clinical")
    ADVANTAGE = "ADVANTAGE", _("Advantage")
    ERP = "ERP", _("ERP")


class FilterAllowedOperations(models.TextChoices):
    """A list of all the logical operations that can be performed on the filter."""

    EQUALS = "EQUALS", _("Equals")
    GREATER_THAN = "GREATER_THAN", _("Greater Than")
    LESS_THAN = "LESS_THAN", _("Less Than")
    LESS_THAN_OR_EQUAL_TO = "LESS_THAN_OR_EQUAL_TO", _("Less Than or Equal To")
    GREATER_THAN_OR_EQUAL_TO = "GREATER_THAN_OR_EQUAL_TO", _("Greater Than or Equal To")


class FilterValueType(models.TextChoices):
    """Indicates how the value of the filter should be handled."""

    CLOSE_ENDED = "CLOSE_ENDED", _("Close Ended")
    OPEN_ENDED = "OPEN_ENDED", _("Open Ended")


class FilterChoiceSource(models.TextChoices):
    """Indicates where the choices should be fetched for close ended values."""

    OCL = "OCL", _("OCL")
    CLOSE_ENDED_CHOICES = "CLOSE_ENDED_CHOICES", _("Close Ended Choices")


class FilterValueDataType(models.TextChoices):
    """An indicator of the data type of the value."""

    NUMBER = "NUMBER", _("Number")
    STRING = "STRING", _("String")
    DATE = "DATE", _("Date")


class FilterDisplayType(models.TextChoices):
    """An indicator to determine an appropriate input component for the frontend."""

    DATE_PICKER = "DATE_PICKER", _("Date Picker")
    TEXT_INPUT = "TEXT_INPUT", _("Text Input")
    NUMBER_INPUT = "NUMBER_INPUT", _("Number Input")
    DROPDOWN = "DROPDOWN", _("Dropdown")


class Filter(OwnerlessAbstractBase):  # type: ignore[django-manager-missing]
    """Represents a filter configuration for querying data sources."""

    name = models.CharField(max_length=50, unique=True)
    source = models.CharField(max_length=64, choices=FilterSource.choices)
    allowed_operations = ArrayField(models.CharField(max_length=64))
    value_type = models.CharField(max_length=64, choices=FilterValueType.choices)
    value_data_type = models.CharField(
        max_length=64, choices=FilterValueDataType.choices
    )
    choice_source = models.CharField(
        max_length=64, choices=FilterChoiceSource.choices, blank=True, null=True
    )
    display_type = models.CharField(max_length=64, choices=FilterDisplayType.choices)
    close_ended_choices = models.JSONField(
        blank=True,
        null=True,
        help_text="stores the choices available for close ended filters.",
        validators=[validate_close_ended_choices],
    )
    ocl_query_options = models.JSONField(
        blank=True,
        null=True,
        help_text="""
        stores the configuration options that help in limiting results
        to those relevant for a filter when making a request to the OCL instance
        """,
    )
    cube_config = models.JSONField(
        blank=True,
        null=True,
        help_text="""
        stores the configuration options that help
        in building/making a query meant for cube
        """,
    )

    model_validators = ["validate_close_ended_choices"]

    def validate_close_ended_choices(self) -> None:
        """Validate close ended choices are provided."""
        if (
            self.choice_source == FilterChoiceSource.CLOSE_ENDED_CHOICES
            and self.close_ended_choices is None
        ):
            raise ValidationError(
                message={"choices": "Close ended choices must be provided"}
            )


class FilterGroup(AbstractBase, OrgUnitIdsMixin):
    """Used to bundle multiple filters together."""

    name = models.CharField(max_length=50)
    segment = models.ForeignKey(
        "segments.Segment",
        on_delete=models.CASCADE,
        related_name="filter_groups",
    )

    class Meta:
        """Set model options."""

        ordering = ("-updated", "-created")


class FilterGroupFilter(AbstractBase, OrgUnitIdsMixin):
    """Stores the value and operation selected for a specific filter."""

    filter_group = models.ForeignKey(
        FilterGroup, on_delete=models.CASCADE, related_name="filters"
    )
    filter = models.ForeignKey(
        Filter, on_delete=models.CASCADE, related_name="filter_groups"
    )
    operation = models.CharField(
        max_length=64,
        choices=FilterAllowedOperations.choices,
        help_text="the operation to be applied to this filter within the group.",
    )
    value = models.CharField(max_length=256)
