"""Prescriptions model."""
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from sil_advantage.common.models import (
    AbstractBase,
    OrgUnitIdsMixin,
    TransitionValidationMixin,
)
from sil_advantage.integrations.mixins import RemoteObjectMixin
from sil_advantage.patients.models import Patient
from sil_advantage.visits.models import Queue

PRESCRIPTION_TRANSITION_GRAPHS = {
    "ACTIVE": ["COMPLETED"],
}


class PrescriptionStatus(models.TextChoices):
    """Attributes that define prescription status choice."""

    ACTIVE = "ACTIVE", _("Active")
    COMPLETED = "COMPLETED", _("Completed")


class PrescriptionTransitionStatus(models.TextChoices):
    """Attributes that define prescription transition status."""

    ACTIVE = "ACTIVE", _("Active")
    COMPLETED = "COMPLETED", _("Completed")


class PrescriptionTransitionLogStatus(AbstractBase):
    """Keeps track of prescription transition logs state."""

    prescription = models.ForeignKey(
        "Prescription",
        on_delete=models.PROTECT,
        related_name="prescription_transition_logs",
    )
    status = models.CharField(max_length=250, choices=PrescriptionStatus.choices)
    status_from = models.CharField(
        max_length=250,
        choices=PrescriptionTransitionStatus.choices,
    )
    status_to = models.CharField(
        max_length=250,
        choices=PrescriptionTransitionStatus.choices,
    )


class Prescription(  # type: ignore
    RemoteObjectMixin,
    TransitionValidationMixin,
    OrgUnitIdsMixin,
    AbstractBase,
):
    """Holds information about a prescription."""

    patient = models.ForeignKey(
        Patient, related_name="prescriptions", on_delete=models.PROTECT
    )
    queue = models.ForeignKey(Queue, related_name="+", on_delete=models.PROTECT)
    status = models.CharField(
        choices=PrescriptionStatus.choices,
        default=PrescriptionStatus.ACTIVE,
        null=False,
    )
    medication_name = models.CharField(max_length=250, null=False)

    # clinical medication request ID
    medication_request_id = models.UUIDField(null=True, blank=True)

    _remote_obj_refs = {
        "CLINICAL_SERVICE": [
            (
                "prescription",
                {
                    "medication_request_id": "id",
                },
            )
        ],
    }

    # async_enabled = settings.VISIT_ASYNC_ENABLED

    _transition_graph = PRESCRIPTION_TRANSITION_GRAPHS
    _transition_field = "status"
    _transition_log_model = PrescriptionTransitionLogStatus
    _transition_log_model_fk_field = "prescription"

    @property
    def dosage(self) -> models.QuerySet["DosageInstruction"]:
        """Retrieve the related DosageInstruction instances."""
        return self.dosages.all()

    @property
    def clinical_service_prescription_payload(self) -> dict:
        """Build the payload for the medication request."""
        dosage_instructions = [
            {
                "route": dosage.route,
                "doseQuantity": dosage.dose_quantity,
                "doseUnit": dosage.dose_unit,
                "period": dosage.period,
                "periodUnit": dosage.period_unit,
                "frequency": dosage.frequency,
                "duration": dosage.duration,
                "durationUnit": dosage.duration_unit,
                "startDate": dosage.start_date.isoformat()
                if dosage.start_date
                else None,
                "endDate": dosage.end_date.isoformat() if dosage.end_date else None,
                "condition": dosage.condition,
                "patientInstruction": dosage.patient_instruction,
                "additionalInstruction": dosage.additional_instruction or [],
                "asNeeded": False,
            }
            for dosage in self.dosages.all()
        ]

        payload: dict = {
            "input": {
                "encounterID": str(self.queue_id),
                "priority": "routine",
                "medicationName": self.medication_name,
                "dosageInstructions": dosage_instructions,
            }
        }

        return payload

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Override save to ensure synchronization with remote systems."""
        super().save(*args, **kwargs)


class DosageInstruction(AbstractBase):
    """Holds information about a dose."""

    route = models.CharField(max_length=255, blank=True, null=True)
    dose_quantity = models.FloatField(blank=True, null=True)
    dose_unit = models.CharField(max_length=50, blank=True, null=True)
    period = models.CharField(max_length=50, blank=True, null=True)
    period_unit = models.CharField(max_length=50, blank=True, null=True)
    frequency = models.IntegerField(blank=True, null=True)
    duration = models.CharField(max_length=50, blank=True, null=True)
    duration_unit = models.CharField(max_length=50, blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    condition = models.CharField(max_length=255, blank=True, null=True)
    patient_instruction = models.TextField(blank=True, null=True)
    additional_instruction = models.JSONField(blank=True, null=True)
    prescription = models.ForeignKey(
        Prescription, max_length=250, on_delete=models.PROTECT, related_name="dosages"
    )

    model_validators = [
        "validate_start_date_is_before_end_date",
        "validate_end_date_not_in_past",
    ]

    def validate_start_date_is_before_end_date(self) -> None:
        """Ensure end date is greater than start date."""
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                error_msg = "Dosage end date must be greater than the start date."
                raise ValidationError(error_msg)

    def validate_end_date_not_in_past(self) -> None:
        """Ensure the end date is not in the past."""
        now = timezone.now().date()
        if self.end_date is not None:
            if self.end_date < now:
                error_msg = "Dosage end date cannot be in the past"
                raise ValidationError(error_msg)
