"""Segment messaging models."""

from __future__ import annotations

import json
import logging
import uuid
import zoneinfo
from datetime import time
from typing import Any

from cron_converter import Cron
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone, translation
from django_celery_beat.models import (
    ClockedSchedule,
    CrontabSchedule,
    PeriodicTask,
)
from jinja2 import Environment
from sil_cacheable.orm import CacheableManager
from sil_transitions import TransitionAndLogMixin
from tree_queries.models import TreeNode

from sil_advantage.common.models import AbstractBase, OrgUnitIdsMixin
from sil_advantage.notifications.sms.models import SMS, SenderID
from sil_advantage.notifications.sms.tasks import send_sms
from sil_advantage.sil_auth.models import SILUser

from .constants import (
    SegmentMemberStatus,
    SegmentMessageDeliveryType,
    SegmentMessageStatus,
    SegmentStatus,
)
from .segments import Segment, SegmentMember
from .template_variables import generate_context_data

MESSAGE_TEMPLATE_STATUS_TRANSITION_GRAPH = {
    "DRAFT": ["ACTIVE"],
    "ACTIVE": ["DRAFT", "RETIRED"],
    "RETIRED": ["ACTIVE"],
}

LOGGER = logging.getLogger(__name__)

jinja_env = Environment()


class MessageTemplateCategories(models.TextChoices):
    """Available categories."""

    INSTANT = "INSTANT", "Instant message."
    GENERAL = "GENERAL", "General message."


class MessageTemplateType(models.TextChoices):
    """Available message template types."""

    SEQUENCED = "SEQUENCED", "A sequenced message template."
    SINGULAR = "SINGULAR", "A standalone message"


def get_next_sequence_message(
    member: SegmentMember, segment_message: MessageTemplate
) -> None | MessageTemplate:
    """The next message that a user receives in the sequence."""
    last_sent_message = (
        member.sent_messages.filter(
            sequence_message=segment_message, sms__state__in=["DELIVERED", "SENT"]
        )
        .order_by("dispatched_at")
        .last()
    )
    if last_sent_message is None:
        return segment_message

    message = last_sent_message.message_template

    return message.children.first()


class MessageTemplateTransitionLog(AbstractBase):
    """Tracks changes to segment for tracking purposes."""

    message_template = models.ForeignKey(
        "MessageTemplate",
        on_delete=models.PROTECT,
        related_name="message_template_logs",
    )
    status_to = models.CharField(max_length=16)
    status_from = models.CharField(max_length=16)


class MessageTemplate(TransitionAndLogMixin, OrgUnitIdsMixin, AbstractBase, TreeNode):  # type: ignore[django-manager-missing]
    """A template for messages that are sent out."""

    name = models.CharField(max_length=150)
    template = models.TextField()
    message_type = models.CharField(max_length=64, choices=MessageTemplateType.choices)
    category = models.CharField(
        max_length=32,
        choices=MessageTemplateCategories.choices,
        default=MessageTemplateCategories.GENERAL,
    )
    status = models.CharField(
        max_length=64,
        choices=SegmentMessageStatus.choices,
        default=SegmentMessageStatus.DRAFT,
    )

    model_validators = ["validate_sequenced_message"]

    _transition_field = "status"
    _transition_log_model_fk_field = "message_template"
    _transition_log_model = MessageTemplateTransitionLog
    _transition_graph = MESSAGE_TEMPLATE_STATUS_TRANSITION_GRAPH

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

        latest_log = MessageTemplateTransitionLog.objects.filter(
            message_template=self
        ).latest("created")
        latest_log.updated_by = updated_by_id
        latest_log.save()

    class Meta:
        """Set model options."""

        ordering = ("-updated", "-created")

    def validate_sequenced_message(self) -> None:
        """Run validations against sequenced messages."""
        if self.parent and self.parent.has_sequence and self._state.adding:
            msg = """
            Parent message has an existing sequenced message.
            It cannot have multiple messages in the same sequence
            """
            message = {"parent_message": msg}
            raise ValidationError(message=message)

    @property
    def has_sequence(self) -> bool:
        """Returns true if a child/sequence template exists."""
        return self.children.exists()

    def send_message(
        self,
        recipient: SegmentMember,
        delivery_type: SegmentMessageDeliveryType,
        sender: SenderID | None = None,
        segment_message: SegmentMessage | None = None,
        intention: str = "BROADCAST",
    ) -> None:
        """Sends a message to a recipient via SMS.

        It renders a message template using the recipient's details added to the context
        and sends the message provided they have given consent.
        The message delivery details are recorded in the database.

        Args:
            recipient (SegmentMember):
                The member of a segment who will receive the message.
            sender (SenderID | None):
                The sender to use when sending out the message if configured.
            intention (str):
                The intention to use when sending out the message if configured.
            delivery_type (SegmentMessageDeliveryType):
                The delivery type of the message and determines template used
            segment_message (SegmentMessage):
                The Segment Message the message will be linked back to.

        Note:
        - Currently supported models that can be used as placeholders in the template:
                1. Person
        - Calculated fields(model properties) are not accounted for.
        """
        message_template = self
        system_admin = SILUser.objects.get(email=settings.SYSTEM_ADMIN_EMAIL).id

        person = recipient.person

        has_consent_for_sms = person.person_contacts.filter(
            contact_type="phone_number", consent_to_contact_given=True
        ).exists()

        language_preference = (
            person.language
            if person.language is not None
            else settings.MODELTRANSLATION_DEFAULT_LANGUAGE
        )
        with translation.override(language_preference):
            if getattr(self, f"template_{language_preference}") is None:
                error_msg = (
                    f"Template: {self.id} ({self.name}) has no "
                    f"{language_preference} translation."
                )
                LOGGER.warning(error_msg)
                return
            if (
                person.phone_number
                and has_consent_for_sms
                and recipient.status == SegmentMemberStatus.CONFIRMED
                and recipient.segment.status == SegmentStatus.ACTIVE
                and self.status == SegmentMessageStatus.ACTIVE
            ):
                context = generate_context_data(recipient)

                if delivery_type == SegmentMessageDeliveryType.SCHEDULED_RECURRENT:
                    next_message = get_next_sequence_message(
                        member=recipient, segment_message=self
                    )
                    if next_message is None:
                        return

                    sequence_message = self
                    message_template = next_message
                    template_string = next_message.template
                else:
                    template_string = self.template
                    sequence_message = None

                template = jinja_env.from_string(template_string)
                message = template.render(**context)

                sender_id: uuid.UUID | None = None

                if sender:
                    sender_id = sender.id

                data = {
                    "member": recipient,
                    "sequence_message": sequence_message,
                    "dispatched_at": timezone.now(),
                    "message_template": message_template,
                    "message": message,
                    "segment_message": segment_message,
                    "organisation": person.organisation,
                    "branch_id": person.branch_id,
                    "created_by": system_admin,
                    "updated_by": system_admin,
                }

                segment_message_delivery_obj = SegmentMessageDelivery.objects.create(
                    **data
                )
                send_sms.apply_async(
                    queue=settings.CELERY_DEFAULT_QUEUE,
                    priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
                    args=(
                        intention,
                        message,
                        [person.phone_number],
                        person.organisation.slade_code,
                        person.branch_id,
                        person.workstation_id,
                    ),
                    kwargs={
                        "sender_id": sender_id,
                        "model_name": "segments.segmentmessagedelivery",
                        "model_obj_pk": segment_message_delivery_obj.id,
                    },
                )


class SegmentMessage(AbstractBase):  # type: ignore[django-manager-missing]
    """Links a message template to a segment."""

    template = models.ForeignKey(
        MessageTemplate,
        on_delete=models.PROTECT,
    )
    segment = models.ForeignKey(
        Segment, on_delete=models.PROTECT, related_name="segment_messages"
    )
    sender = models.ForeignKey(
        SenderID,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
    )
    send_on_segment_join = models.BooleanField(
        default=False,
        help_text="Indicates whether the message is be sent when a new member joins.",
    )

    delivery_type = models.CharField(
        max_length=64, choices=SegmentMessageDeliveryType.choices
    )
    scheduled_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When a scheduled one time message should be sent.",
    )
    sequence_interval = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="""
        Holds the sequencing interval to send scheduled recurrent messages.
        Specifies units of time of when to send an sms i.e minute, hour,
        day_of_week, day_of_month, month_of_year.
        Follows the crontab format using a dict to store the args
        Example:
        A sequential message sent out on wednesday every week
        """,
    )

    task = models.ForeignKey(
        PeriodicTask,
        blank=True,
        null=True,
        related_name="+",
        on_delete=models.PROTECT,
    )

    objects: models.Manager["SegmentMessage"] = CacheableManager()

    model_validators = [
        "validate_delivery_type_scheduling",
        "validate_segment_is_not_retired",
        "validate_sender_availability",
    ]

    class Meta:
        """Set model options."""

        ordering = ("-updated", "-created")

    def validate_segment_is_not_retired(self) -> None:
        """Validates that a segment is not retired before adding a message."""
        if self.segment.status == SegmentStatus.RETIRED:
            msg = """
            Message cannot be added to a retired segment!
            """
            message = {"segment": msg}
            raise ValidationError(message=message)

    def validate_delivery_type_scheduling(self) -> None:
        """Validates the message template based on the delivery type."""
        if (
            self.delivery_type == SegmentMessageDeliveryType.SCHEDULED_ONE_TIME
            and self.scheduled_at is None
        ):
            msg = """
            Scheduling a one time message requires `scheduled_at` to be provided
            """
            message = {"scheduled_at": msg}
            raise ValidationError(message=message)

        if (
            self.delivery_type == SegmentMessageDeliveryType.SCHEDULED_RECURRENT
            and self.sequence_interval is None
        ):
            msg = """
            Scheduling a recurrent message requires `sequence_interval` to be provided
            """
            message = {"sequence_interval": msg}
            raise ValidationError(message=message)

    def validate_sender_availability(self) -> None:
        """Validates sender availability before sending or scheduling."""
        if self.sender:
            if self.delivery_type == SegmentMessageDeliveryType.INSTANT:
                scheduled_time = timezone.localtime(timezone.now()).time()

            if self.delivery_type == SegmentMessageDeliveryType.SCHEDULED_ONE_TIME:
                scheduled_time = timezone.localtime(self.scheduled_at).time()

            if self.delivery_type == SegmentMessageDeliveryType.SCHEDULED_RECURRENT:
                interval = Cron(str(self.sequence_interval)).to_string().split(" ")
                scheduled_time = time(hour=int(interval[1]), minute=int(interval[0]))

            is_availble = self.sender.is_available(scheduled_time)
            if not is_availble:
                msg = f"""
                Unable to schedule message! Selected SenderID is unavailable
                at {scheduled_time.strftime("%-I:%M %p")}
                """
                message = {"sender": msg}
                raise ValidationError(message=message)

    def _is_schedule_updated(self) -> bool:
        """Checks if an existing schedule is being updated."""
        original = self.__class__.objects.get(pk=self.pk)

        # edge cases :-(
        if original.delivery_type != self.delivery_type:
            raise ValidationError(
                message={
                    "delivery_type": "Cannot change delivery type for a segment message"
                }
            )

        # INSTANT messages have no task
        task = original.task
        if not task:
            return False

        if self.delivery_type == SegmentMessageDeliveryType.SCHEDULED_RECURRENT:
            has_changed = original.sequence_interval != self.sequence_interval

        if self.delivery_type == SegmentMessageDeliveryType.SCHEDULED_ONE_TIME:
            has_changed = original.scheduled_at != self.scheduled_at

        if not has_changed:
            return False

        task.enabled = False
        task.save()

        return True

    @transaction.atomic
    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save a segment message."""
        self.full_clean()
        is_new = self._state.adding

        if is_new is True or self._is_schedule_updated() is True:
            if self.delivery_type == SegmentMessageDeliveryType.SCHEDULED_RECURRENT:
                try:
                    cron = Cron(str(self.sequence_interval)).to_string().split(" ")
                except ValueError:
                    msg = f"Invalid cron expression: {str(self.sequence_interval)}"
                    message = {"sequence_interval": msg}

                    raise ValidationError(message=message)

                schedule, _ = CrontabSchedule.objects.get_or_create(
                    minute="".join(cron[0]),
                    hour="".join(cron[1]),
                    day_of_month="".join(cron[2]),
                    month_of_year="".join(cron[3]),
                    day_of_week="".join(cron[4]),
                    timezone=zoneinfo.ZoneInfo(settings.TIME_ZONE),
                )

                task_name = (
                    f"{self.delivery_type}: {self.segment.id}-{self.template.id}"
                )
                task_name += f"-{str(uuid.uuid4())}"

                task = PeriodicTask.objects.create(
                    crontab=schedule,
                    name=task_name,
                    task="sil_advantage.segments.tasks.send_segment_scheduled_recurrent_messages",
                    args=json.dumps([str(self.id)]),
                    priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
                    queue=settings.CELERY_DEFAULT_QUEUE,
                )

                self.task = task

            if self.delivery_type == SegmentMessageDeliveryType.SCHEDULED_ONE_TIME:
                schedule, _ = ClockedSchedule.objects.get_or_create(
                    clocked_time=self.scheduled_at
                )

                task_name = (
                    f"{self.delivery_type}: {self.segment.id}-{self.template.id}"
                )
                task_name += f"-{str(uuid.uuid4())}"

                task = PeriodicTask.objects.create(
                    clocked=schedule,
                    name=task_name,
                    task="sil_advantage.segments.tasks.send_segment_scheduled_one_time_messages",
                    one_off=True,
                    args=json.dumps([str(self.id)]),
                    priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
                    queue=settings.CELERY_DEFAULT_QUEUE,
                )

                self.task = task

            if self.delivery_type == "INSTANT":
                from sil_advantage.segments.tasks import (
                    send_segment_instant_messages,
                )

                # Send instant messages that'll go out after `SEGMENT_DELAY_BEFORE_SENDING_INSTANT_MESSAGE` seconds # noqa: B950
                send_segment_instant_messages.apply_async(
                    queue=settings.CELERY_DEFAULT_QUEUE,
                    priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
                    countdown=settings.SEGMENT_DELAY_BEFORE_SENDING_INSTANT_MESSAGE,
                    args=(self.id,),
                )

        super().save(*args, **kwargs)


class SegmentMessageDelivery(OrgUnitIdsMixin, AbstractBase):
    """Tracks message sending for each segment member."""

    member = models.ForeignKey(
        SegmentMember, on_delete=models.PROTECT, related_name="sent_messages"
    )
    # Initial message for a sequence
    sequence_message = models.ForeignKey(
        MessageTemplate,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    dispatched_at = models.DateTimeField(auto_now_add=True)
    message = models.TextField()
    message_template = models.ForeignKey(
        MessageTemplate,
        on_delete=models.PROTECT,
        related_name="messages",
        help_text="""
        Template used to generate the message.
        """,
    )
    sms = models.ForeignKey(
        SMS,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="""
        Holds a reference of the SMS that will be used to track
        real-time delivery statuses.
        """,
    )
    segment_message = models.ForeignKey(
        SegmentMessage,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="segment_message_deliveries",
    )

    objects: models.Manager["SegmentMessageDelivery"] = CacheableManager()

    class Meta:
        """Set model options."""

        ordering = ("-updated", "-created")
