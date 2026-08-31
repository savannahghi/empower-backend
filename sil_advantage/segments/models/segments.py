"""Core segments models."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from jinja2 import Environment
from jsonschema import ValidationError as JSONSchemaValidationError
from jsonschema import validate
from sil_cacheable.orm import CacheableManager
from sil_transitions import TransitionAndLogMixin

from sil_advantage.common.models import AbstractBase, OrgUnitIdsMixin, Person
from sil_advantage.common.models.common_models import OperatingRegion

from .constants import (
    SEGMENT_ATTRIBUTES_SCHEMA,
    SegmentLabels,
    SegmentMemberAdditionAttributes,
    SegmentMemberStatus,
    SegmentStatus,
)
from .filters import FilterExecutionStatus

SEGMENT_STATUS_TRANSITION_GRAPH = {
    "DRAFT": ["ACTIVE"],
    "ACTIVE": ["DRAFT", "RETIRED"],
    "RETIRED": ["ACTIVE"],
}

SEGMENT_MEMBER_STATUS_TRANSITION_GRAPH = {
    "DRAFT": ["CONFIRMED"],
    "CONFIRMED": ["DRAFT", "RETIRED"],
    "RETIRED": ["CONFIRMED"],
}

FILTER_EXECUTION_STATUS_TRANSITION_GRAPH = {
    "PENDING": ["IN_PROGRESS"],
    "IN_PROGRESS": ["SUCCESS", "FAILED"],
    "FAILED": ["IN_PROGRESS"],
    "SUCCESS": ["IN_PROGRESS"],
}

jinja_env = Environment()


def validate_segment_attributes(value: dict) -> None:
    """Validates that the provided attributes for a schema are valid."""
    try:
        validate(instance=value, schema=SEGMENT_ATTRIBUTES_SCHEMA)
    except JSONSchemaValidationError as e:
        raise ValidationError(message=e.message)


class SegmentClassification(models.TextChoices):
    """Attributes that define the status of a segment."""

    JOURNEY = "JOURNEY", "Segment that belongs to a journey"
    DYNAMIC = "DYNAMIC", "Automatically update their members based on its criteria"
    STATIC = (
        "STATIC",
        "Add records which meet a set criteria at the point when the list is saved",
    )


class SegmentTransitionLog(AbstractBase):
    """Tracks changes to segment for tracking purposes."""

    segment = models.ForeignKey(
        "Segment", on_delete=models.PROTECT, related_name="segment_logs"
    )
    status_to = models.CharField(max_length=16)
    status_from = models.CharField(max_length=16)


class FilterExecutionTransitionLog(AbstractBase):
    """Tracks changes to the filter execution status for tracking purposes."""

    segment = models.ForeignKey(
        "Segment", on_delete=models.PROTECT, related_name="filter_execution_logs"
    )
    status_from = models.CharField(max_length=16)
    status_to = models.CharField(max_length=16)
    reason = models.TextField(blank=True, null=True)

    class Meta:
        """Set model options."""

        ordering = ("-created",)


class Segment(TransitionAndLogMixin, OrgUnitIdsMixin, AbstractBase):  # type: ignore[django-manager-missing]
    """A segment."""

    name = models.CharField(max_length=48)
    status = models.CharField(
        max_length=64, choices=SegmentStatus.choices, default=SegmentStatus.ACTIVE
    )
    label = models.CharField(
        max_length=64, choices=SegmentLabels.choices, blank=True, null=True
    )
    classification = models.CharField(
        max_length=64,
        choices=SegmentClassification.choices,
        default=SegmentClassification.STATIC,
    )
    description = models.CharField(max_length=256, blank=True, null=True)
    attributes = models.JSONField(
        blank=True,
        null=True,
        help_text="stores characteristics of a segment as defined by the user.",
        validators=[validate_segment_attributes],
    )
    members = models.ManyToManyField(
        Person,
        through="SegmentMember",
        through_fields=("segment", "person"),
        related_name="segments",
    )
    messages = models.ManyToManyField(
        "MessageTemplate",
        through="SegmentMessage",
        through_fields=("segment", "template"),
        related_name="segments",
    )
    welcome_message_template = models.ForeignKey(
        "MessageTemplate",
        on_delete=models.PROTECT,
        related_name="segment_welcome_messages",
        null=True,
        blank=True,
    )
    send_welcome_message_notification = models.BooleanField(blank=True, null=True)
    filter_execution_status = models.CharField(
        max_length=64, choices=FilterExecutionStatus.choices, blank=True, null=True
    )
    ussd_enabled = models.BooleanField(blank=True, null=True)

    objects: models.Manager["Segment"] = CacheableManager()

    class Meta:
        """Set model options."""

        ordering = ("-updated", "-created")

    @cached_property
    def member_count(self) -> int:
        """Returns the count of members within the segment."""
        return self.segment_memberships.filter(
            status=SegmentMemberStatus.CONFIRMED
        ).count()

    _transition_field = "status"
    _transition_log_model_fk_field = "segment"
    _transition_log_model = SegmentTransitionLog
    _transition_graph = SEGMENT_STATUS_TRANSITION_GRAPH

    def transition_log_data(self) -> dict:
        """Prepare a transition log data dict that is ready to be saved."""
        data = super().transition_log_data()
        data.update(
            {
                "created_by": self.updated_by,
                "updated_by": self.updated_by,
                "organisation": self.organisation,
            }
        )
        return data

    def post_transition(
        self, data: dict, transition_from: str, transition_to: str
    ) -> None:
        """Override this method to add functionality to follow a transition."""
        updated_by_id = data["updated_by"]

        latest_log = SegmentTransitionLog.objects.filter(segment=self).latest("created")
        latest_log.updated_by = updated_by_id
        latest_log.save()

    _filter_execution_transition_graph = FILTER_EXECUTION_STATUS_TRANSITION_GRAPH

    def log_filter_execution_status_transition(
        self, new_status: str, reason: str = ""
    ) -> None:
        """Log the transition of filter execution status."""
        if self.status == SegmentStatus.RETIRED:
            raise ValidationError("Cannot execute filters on a deactivated segment.")

        default_status = FilterExecutionStatus.choices[0][0]
        current_status = self.filter_execution_status or default_status
        if new_status in self._filter_execution_transition_graph.get(
            current_status, []
        ):
            FilterExecutionTransitionLog.objects.create(
                segment=self,
                status_from=current_status,
                status_to=new_status,
                reason=reason,
                created_by=self.updated_by,
                updated_by=self.updated_by,
                organisation=self.organisation,
            )
            self.filter_execution_status = new_status
            self.save()
        else:
            raise ValidationError(
                f"Invalid transition from {current_status} to {new_status}."
            )


class SegmentUpload(OrgUnitIdsMixin, AbstractBase):
    """Segment Upload."""

    segment = models.ForeignKey(
        Segment, on_delete=models.PROTECT, related_name="segment_uploads"
    )

    file_upload = models.ForeignKey(
        "patients.PatientListUpload", on_delete=models.PROTECT, related_name="+"
    )

    extra_headers = ArrayField(models.CharField(max_length=64), blank=True, null=True)
    objects: models.Manager["SegmentUpload"] = CacheableManager()


class SegmentMemberTransitionLog(AbstractBase):
    """Tracks changes to a segment member for tracking purposes."""

    segment_member = models.ForeignKey(
        "SegmentMember", on_delete=models.PROTECT, related_name="segment_member_logs"
    )
    status_to = models.CharField(max_length=16)
    status_from = models.CharField(max_length=16)


class SegmentMember(TransitionAndLogMixin, OrgUnitIdsMixin, AbstractBase):  # type: ignore[django-manager-missing]
    """Segment Member."""

    person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="segment_memberships"
    )
    segment = models.ForeignKey(
        Segment, on_delete=models.PROTECT, related_name="segment_memberships"
    )
    status = models.CharField(
        max_length=64,
        choices=SegmentMemberStatus.choices,
        default=SegmentMemberStatus.CONFIRMED,
    )
    # Segment member addition attribution
    source = models.CharField(
        null=True,
        blank=True,
        choices=SegmentMemberAdditionAttributes.choices,
        max_length=50,
        default=SegmentMemberAdditionAttributes.MANUAL,
    )
    extra_data = models.JSONField(
        blank=True,
        null=True,
        help_text="stores extra information related to a segment member.",
    )
    member_associated_region = models.ForeignKey(
        OperatingRegion,
        related_name="member_operating_region",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    enrolled_at = models.DateTimeField(default=timezone.now)

    objects: models.Manager["SegmentMember"] = CacheableManager()

    model_validators = ["validate_segment_is_not_retired"]

    _transition_field = "status"
    _transition_log_model_fk_field = "segment_member"
    _transition_log_model = SegmentMemberTransitionLog
    _transition_graph = SEGMENT_MEMBER_STATUS_TRANSITION_GRAPH

    def transition_log_data(self) -> dict:
        """Prepare a transition log data dict that is ready to be saved."""
        data = super().transition_log_data()
        data.update(
            {
                "created_by": self.updated_by,
                "updated_by": self.updated_by,
                "organisation": self.organisation,
            }
        )
        return data

    def post_transition(
        self, data: dict, transition_from: str, transition_to: str
    ) -> None:
        """Override this method to add functionality to follow a transition."""
        updated_by_id = data["updated_by"]

        latest_log = SegmentMemberTransitionLog.objects.filter(
            segment_member=self
        ).latest("created")
        latest_log.updated_by = updated_by_id
        latest_log.save()

    class Meta:
        """Set model options."""

        unique_together = ("person", "segment")
        ordering = ("-updated", "-created")

    def validate_segment_is_not_retired(self) -> None:
        """Validates that a segment is not retired before adding a member."""
        if self.segment.status == SegmentStatus.RETIRED:
            msg = """
            Member cannot be added to a retired segment!
            """
            message = {"segment": msg}
            raise ValidationError(message=message)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save a segment member."""
        is_new = self._state.adding

        if is_new:
            from sil_advantage.segments.tasks import (
                send_segment_joining_messages,
                send_segment_welcome_message,
            )

            countdown = settings.SEGMENT_DELAY_BEFORE_SENDING_INSTANT_MESSAGE

            if (
                self.segment.send_welcome_message_notification
                and self.segment.welcome_message_template
            ):
                send_segment_welcome_message.apply_async(
                    queue=settings.CELERY_DEFAULT_QUEUE,
                    priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
                    countdown=countdown,
                    args=(self.segment.welcome_message_template.id, self.id),
                )
                # increment countdown for joining messages
                countdown += 60

            send_segment_joining_messages.apply_async(
                queue=settings.CELERY_DEFAULT_QUEUE,
                priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
                countdown=countdown,
                args=(self.id,),
            )

        super().save(*args, **kwargs)
