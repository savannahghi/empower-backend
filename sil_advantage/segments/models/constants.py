"""Constants."""
from django.db import models


class SegmentLabels(models.TextChoices):
    """Available choices for system-defined segments."""

    CERVICAL_CANCER_TIPS = "CERVICAL_CANCER_TIPS", "Cervical Cancer General Tips"
    CERVICAL_CANCER_HIGH_RISK = (
        "CERVICAL_CANCER_HIGH_RISK",
        "High Risk of Cervical Cancer",
    )
    CERVICAL_CANCER_LOW_RISK = "CERVICAL_CANCER_LOW_RISK", "Low Risk of Cervical Cancer"
    CERVICAL_CANCER_POSITIVE = (
        "CERVICAL_CANCER_POSITIVE",
        "Positive for Cervical Cancer",
    )
    BREAST_CANCER_TIPS = "BREAST_CANCER_TIPS", "Breast Cancer General Tips"
    BREAST_CANCER_HIGH_RISK = (
        "BREAST_CANCER_HIGH_RISK",
        "High Risk of Breast Cancer",
    )
    BREAST_CANCER_LOW_RISK = "BREAST_CANCER_LOW_RISK", "Low Risk of Breast Cancer"
    BREAST_CANCER_POSITIVE = (
        "BREAST_CANCER_POSITIVE",
        "Positive for Breast Cancer",
    )
    BREAST_CANCER_AVERAGE_RISK = (
        "BREAST_CANCER_AVERAGE_RISK",
        "Average Risk of Breast Cancer",
    )


SEGMENT_ATTRIBUTES_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Generated schema for Root",
    "type": "object",
    "properties": {
        "demographics": {
            "type": "object",
            "properties": {
                "gender": {"type": "array", "items": {"type": "string"}},
                "minimum_age": {"type": "number"},
                "maximum_age": {"type": "number"},
            },
        }
    },
    "required": ["demographics"],
}


SEGMENT_MESSAGE_DELIVERY_STATUS = [("SCHEDULED", "SCHEDULED"), ("SENT", "SENT")]


class SegmentMemberAdditionAttributes(models.TextChoices):
    """Attributes that define the origin of a segment member."""

    UPLOAD = "UPLOAD", "Members added via file upload"
    MANUAL = "MANUAL", "Members added manually"
    AUTOMATIC = "AUTOMATIC", "Members added via filters"
    USSD = "USSD", "Members added via USSD"


class SegmentMessageDeliveryType(models.TextChoices):
    """Available choices for segment message delivery type."""

    INSTANT = "INSTANT", "Sends message immediately"
    SCHEDULED_ONE_TIME = "SCHEDULED_ONE_TIME", "Sends a scheduled message once"
    SCHEDULED_RECURRENT = "SCHEDULED_RECURRENT", "Sends a scheduled message recurrently"


class SegmentMessageStatus(models.TextChoices):
    """Available choices for segment message status."""

    DRAFT = "DRAFT", "Message in draft state"
    ACTIVE = "ACTIVE", "Message in active state"
    RETIRED = "RETIRED", "Message in retired state"


class SegmentMemberStatus(models.TextChoices):
    """Attributes that define the status of a segment member."""

    DRAFT = "DRAFT", "Member in draft state"
    CONFIRMED = "CONFIRMED", "Member in confirmed state"
    RETIRED = "RETIRED", "Member in retired state"


class SegmentStatus(models.TextChoices):
    """Attributes that define the status of a segment."""

    DRAFT = "DRAFT", "Segment in draft state"
    ACTIVE = "ACTIVE", "Segment in active state"
    RETIRED = "RETIRED", "Segment in retired state"
