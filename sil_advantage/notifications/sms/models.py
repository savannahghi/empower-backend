"""SMS models."""

import uuid
from datetime import time
from typing import Any, Optional

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from sil_cacheable.orm import CacheableManager

from sil_advantage.common.models import AbstractBase, OrgUnitIdsMixin
from sil_advantage.common.models.common_models import Attachment
from sil_advantage.common.models.organisation_models import Organisation


class Classification(models.TextChoices):
    """Attributes that define the state of an SMS report."""

    SENDER_ID = "SENDER_ID", "A BulkSMS SenderID"
    INTERACTIVE_SHORTCODE = "INTERACTIVE_SHORTCODE", "An interactive ShortCode"


class ProcessState(models.TextChoices):
    """Attributes that define the type of a SenderID."""

    PENDING = "PENDING", "Report in pending state"
    IN_PROGRESS = "IN_PROGRESS", "Report in progress state"
    COMPLETE = "COMPLETE", "Report in complete state"
    FAILED = "FAILED", "Report in failed state"


SENDER_ID_TYPES = (
    ("PROMOTION", "PROMOTION"),
    ("TRANSACTION", "TRANSACTION"),
)

SMS_STATES = (
    # OUTBOUND SMS
    # The SIL gateway has successfully received the request
    ("QUEUED", "QUEUED"),
    # SIL gateway can't process the request for reasons such as invalid MSISDN
    ("FAILED", "FAILED"),
    # The SMS has been sent to the Telco gateway
    ("SENT", "SENT"),
    # SMS was rejected by the Telco gateway
    ("REJECTED", "REJECTED"),
    # SMS has been delivered to user's phone
    ("DELIVERED", "DELIVERED"),
    # SMS couldn't be delivered to user's phone
    ("UNDELIVERED", "UNDELIVERED"),
    # INBOUND SMS (for OnDemand SMS)
    # SMS has been received from Telco gateway
    ("RECEIVED", "RECEIVED"),
    ("RETRIED", "RETRIED"),
)

DELIVERY_TYPES = (
    ("OUTBOUND", "OUTBOUND"),
    ("INBOUND", "INBOUND"),
)


class SenderID(AbstractBase, OrgUnitIdsMixin):  # type: ignore
    """Holds information on Bulk SMS Senders."""

    name = models.CharField(max_length=255)
    classification = models.CharField(
        max_length=100, choices=Classification.choices, default=Classification.SENDER_ID
    )
    sender_type = models.CharField(max_length=50, choices=SENDER_ID_TYPES)
    start_date = models.DateTimeField(help_text="Date from which the sender is valid.")
    end_date = models.DateTimeField(help_text="Date after which the sender is invalid.")
    available_from = models.TimeField(null=True, blank=True)
    available_to = models.TimeField(null=True, blank=True)

    objects: models.Manager["SenderID"] = CacheableManager()

    model_validators = [
        "validate_start_date_is_before_end_date",
        "validate_start_date_not_in_future",
        "validate_end_date_not_in_past",
    ]

    def __str__(self) -> str:
        """String representation of SenderID."""
        return self.name

    def validate_start_date_is_before_end_date(self) -> None:
        """Ensure end date is greater than start date."""
        if self.start_date > self.end_date:
            error_msg = "SenderID end date must be greater than the start date."
            raise ValidationError(error_msg)

    def validate_start_date_not_in_future(self) -> None:
        """Ensure the start date is not in the future."""
        now = timezone.now()
        if self.start_date > now:
            error_msg = "SenderID start date cannot be in the future."
            raise ValidationError(error_msg)

    def validate_end_date_not_in_past(self) -> None:
        """Ensure the end date is not in the past."""
        now = timezone.now()
        if self.end_date < now:
            error_msg = "SenderID end date cannot be in the past"
            raise ValidationError(error_msg)

    @cached_property
    def service(self) -> str:
        """Return the sender's billable service name.

        Utilized when fetching pricing tables on ERP
        during billing.
        """
        if self.sender_type == "TRANSACTION":
            service = "TRANSACTIONAL_BULK_SMS"
        else:
            service = "PROMOTIONAL_BULK_SMS"
        return service

    @classmethod
    def get_org_sender_ids(
        cls,
        organisation: Organisation,
        branch_id: uuid.UUID,
        sender_type: str,
    ) -> models.QuerySet["SenderID"]:
        """Return an organisations custom sender id.

        Default to Savannah's senders for orgs without any
        custom sender configuration.
        """
        org_sender_id = cls.objects.filter(
            organisation=organisation,
            branch_id=branch_id,
            sender_type=sender_type,
            end_date__gte=timezone.now(),
        )
        if org_sender_id.exists():
            return org_sender_id

        # return a default sender
        if sender_type == "TRANSACTION":
            default_transactional_sender = settings.SIL_COMMS_TRANSACTIONAL_SENDER_ID
            return cls.objects.filter(name=default_transactional_sender)

        default_promotional_sender = settings.SIL_COMMS_PROMOTIONAL_SENDER_ID
        return cls.objects.filter(name=default_promotional_sender)

    @property
    def disabled(self) -> dict[str, bool | str | None]:
        """Validates/checks if a sender ID is enabled for use."""
        now = timezone.localtime(timezone.now()).time()

        if not self.is_available(now):
            _from = self.available_from.strftime("%-I:%M %p")  # type: ignore
            _to = self.available_to.strftime("%-I:%M %p")  # type: ignore

            return {
                "status": True,
                "reason": f"This option is only available from {_from} to {_to}.",
            }

        return {"status": False, "reason": None}

    def is_available(self, check_time: time) -> bool:
        """Check availability of a sender ID given a time."""
        if not self.available_from or not self.available_to:
            return True

        return (self.available_from < check_time) and (self.available_to > check_time)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Override save to include availability."""
        if self._state.adding and self.sender_type != "TRANSACTION":
            self.available_from = time(8)
            self.available_to = time(18)

        return super().save(*args, **kwargs)


class SMS(AbstractBase, OrgUnitIdsMixin):
    """Holds all SMS's sent out from the platform."""

    sender = models.ForeignKey(
        SenderID,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
    )
    message = models.CharField()
    recipients = ArrayField(models.CharField(max_length=20))
    intention = models.CharField(max_length=100)
    state = models.CharField(
        max_length=50, choices=SMS_STATES, null=True, blank=True, default="QUEUED"
    )

    # `sil_comms_id` is the ID SIL Comms assigns to the SMS
    # Used by the callback that updates sms statuses
    sil_comms_sms_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="ID of the SMS assigned on SIL Comms",
    )
    failure_reason = models.CharField(max_length=100, blank=True, null=True)
    delivery_type = models.CharField(
        max_length=10,
        choices=DELIVERY_TYPES,
        default="OUTBOUND",
        help_text="Indicates whether an SMS is inbound or outbound",
    )
    objects: models.Manager["SMS"] = CacheableManager()

    @property
    def from_name(self) -> Optional[str]:
        """Determine the 'from' field based on the delivery type.

        +--------------+----------------+----------------+
        | DeliveryType | 'From' Field    | 'To' Field     |
        +==============+================+================+
        | INBOUND      | Phone Number    | Sender ID      |
        +--------------+----------------+----------------+
        | OUTBOUND     | Sender ID       | Phone Number   |
        +--------------+----------------+----------------+
        """
        if self.delivery_type == "INBOUND":
            return self.recipients[0]
        else:
            return self.sender.name if self.sender else None

    @property
    def to(self) -> Optional[str]:
        """Determine the 'to' field based on the delivery type."""
        if self.delivery_type == "INBOUND":
            return self.sender.name if self.sender else None
        else:
            return self.recipients[0]


class SMSLogReport(OrgUnitIdsMixin, AbstractBase):
    """Holds generated SMS reports."""

    report_file = models.ForeignKey(
        Attachment,
        on_delete=models.PROTECT,
        related_name="+",
        blank=True,
        null=True,
    )
    process_state = models.CharField(
        max_length=30, choices=ProcessState.choices, default="PENDING"
    )
    failure_reason = models.CharField(max_length=100, blank=True, null=True)
