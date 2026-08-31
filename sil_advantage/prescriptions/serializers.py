"""Prescription serializers."""
from typing import Any, Dict

from django.db import transaction
from rest_framework import serializers

from sil_advantage.common.serializers import BaseSerializer
from sil_advantage.prescriptions.models import DosageInstruction, Prescription


class DosageInstructionSerializer(BaseSerializer):
    """Dosage Serializer."""

    class Meta:
        """Serializer options."""

        model = DosageInstruction
        extra_kwargs = {"prescription": {"required": False}}
        fields = "__all__"

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validates the dosage instruction data according to specified rules.

        This method checks the following constraints:
            - If 'duration' is provided, 'duration_unit' must also be provided
            - If 'period' is provided, 'period_unit' must also be provided
            - 'Duration' must be a non-negative value if it exists
            - 'Period' must be a non-negative value if it exists
        """
        if data.get("duration") and not data.get("duration_unit"):
            raise serializers.ValidationError(
                "Duration unit is required if duration is provided."
            )

        if data.get("period") and not data.get("period_unit"):
            raise serializers.ValidationError(
                "Period unit is required if period is provided."
            )

        if data.get("duration") and float(data["duration"]) < 0:
            raise serializers.ValidationError("Duration must be a non-negative value.")

        if data.get("period") and float(data["period"]) < 0:
            raise serializers.ValidationError("Period must be a non-negative value.")

        return data


class PrescriptionSerializer(BaseSerializer):
    """Prescription Serializer."""

    dosage = DosageInstructionSerializer(many=True)

    class Meta:
        """Serializer options."""

        model = Prescription
        fields = [
            "id",
            "medication_name",
            "status",
            "dosage",
            "patient",
            "queue",
        ]

    @transaction.atomic
    def create(self, validated_data: dict) -> Prescription:
        """Create a Prescription and its related DosageInstruction instances."""
        dosage_data = validated_data.pop("dosage", None)
        prescription = super().create(validated_data)
        if not dosage_data:
            return prescription

        for dosage in dosage_data:
            dosage["prescription"] = prescription.id

            dose_data_serializer = DosageInstructionSerializer(
                data=dosage, context={"request": self.context["request"]}
            )
            dose_data_serializer.is_valid(raise_exception=True)
            dose_data_serializer.save()

        return prescription
