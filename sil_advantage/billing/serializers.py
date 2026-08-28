"""Billing serializers."""
from decimal import Decimal
from typing import Any, Dict, Union
from uuid import UUID

from django.conf import settings
from rest_framework import serializers

from sil_advantage.billing import REFUND_REASONS
from sil_advantage.billing.models import (
    BillableItem,
    ClinicalOrder,
    ClinicalOrderTransitionLog,
    Invoice,
    InvoiceTransitionLog,
    Payment,
    Refund,
    RefundLine,
    RefundTransitionLog,
)
from sil_advantage.common.serializers import BaseSerializer


class BillableItemSerializer(BaseSerializer):
    """BillableItem Serializer."""

    sales_order_line_id = serializers.ReadOnlyField()
    sales_invoice_line_id = serializers.ReadOnlyField()

    class Meta:
        """Serialization options."""

        model = BillableItem
        fields = "__all__"

    def create(self, validated_data: Dict[str, Any]) -> Any:
        """Create clinical order if its not passed in the validated data."""
        if "clinical_order" not in validated_data:
            invoice = validated_data.get("invoice", None)
            service_request = invoice.service_request
            clinical_order = service_request.clinical_order
            validated_data["clinical_order"] = clinical_order
        return super().create(validated_data)


class ClinicalOrderTransitionLogSerializer(BaseSerializer):
    """ClinicalOrderTransitionLog Serializer."""

    class Meta:
        """Serialization options."""

        model = ClinicalOrderTransitionLog
        fields = "__all__"


class ClinicalOrderSerializer(BaseSerializer):
    """ClinicalOrder Serializer."""

    sales_order_id = serializers.ReadOnlyField()
    workflow_state = serializers.ReadOnlyField()
    order_lines = BillableItemSerializer(read_only=True, many=True)

    class Meta:
        """Serialization options."""

        model = ClinicalOrder
        fields = "__all__"


class PaymentSerializer(BaseSerializer):
    """Payment Serializer."""

    workflow_state = serializers.ReadOnlyField()
    payment_receipt_id = serializers.UUIDField(required=False)

    class Meta:
        """Serialization options."""

        model = Payment
        fields = "__all__"


class RefundTransitionLogSerializer(BaseSerializer):
    """RefundTransitionLog Serializer."""

    class Meta:
        """Serialization options."""

        model = RefundTransitionLog
        fields = "__all__"


class RefundLineSerializer(BaseSerializer):
    """RefundLine Serializer."""

    sales_credit_note_line_id = serializers.ReadOnlyField()

    class Meta:
        """Serialization options."""

        model = RefundLine
        fields = "__all__"


class RefundSerializer(BaseSerializer):
    """Refund Serializer."""

    sales_credit_note_id = serializers.ReadOnlyField()
    refund_number = serializers.ReadOnlyField()
    workflow_state = serializers.ReadOnlyField()
    refund_lines = RefundLineSerializer(read_only=True, many=True)
    total_amount = serializers.ReadOnlyField(source="amount")
    partially_refunded_amount = serializers.ReadOnlyField(source="refund_amount")
    kra_refund_reason = serializers.SerializerMethodField()

    class Meta:
        """Serialization options."""

        model = Refund
        fields = "__all__"

    def get_kra_refund_reason(self, obj: Any) -> str:
        """Return the reason text based on kra_reason_code."""
        reasons_dict: Dict[Union[int, str], str] = dict(REFUND_REASONS)
        reason_text: str = reasons_dict.get(obj.kra_reason_code, "Unknown")
        return reason_text


class RefundInvoiceLinesInputSerializer(serializers.Serializer):
    """Refund input Line Serializer."""

    id = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=20, decimal_places=settings.DECIMAL_PLACES
    )
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)


class RefundInputSerializer(serializers.Serializer):
    """Refund input Serializer."""

    reason = serializers.CharField()
    kra_reason_code = serializers.CharField()
    invoice_lines: serializers.ListSerializer[
        serializers.UUIDField
    ] = serializers.ListSerializer(
        child=serializers.UUIDField(),
        default=list,
    )


class RefundLineInputSerializer(serializers.Serializer):
    """Refund input Serializer."""

    reason = serializers.CharField()
    kra_reason_code = serializers.CharField()
    invoice_lines = RefundInvoiceLinesInputSerializer(many=True)

    def validate(self, data: Dict) -> Dict:
        """Validate refund line input data data."""
        invoice_lines = data.get("invoice_lines", [])

        for line in invoice_lines:
            invoice_line_id = line.get("id")
            amount = line.get("amount")
            quantity = line.get("quantity")

            invoice_line = self.get_invoice_line(invoice_line_id)
            self.validate_quantity(quantity, invoice_line.quantity)
            self.validate_amount(amount, invoice_line.price)

        return data

    def get_invoice_line(self, invoice_line_id: UUID) -> BillableItem:
        """Get the BillableItem or raise an error if it does not exist."""
        try:
            return BillableItem.objects.get(id=invoice_line_id)
        except BillableItem.DoesNotExist:
            raise serializers.ValidationError(
                {"detail": "BillableItem with this id does not exist."}
            )

    def validate_quantity(self, quantity: Decimal, available_quantity: Decimal) -> None:
        """Validate the quantity of the refund line."""
        if quantity < 0:
            raise serializers.ValidationError(
                {"detail": "Quantity cannot be negative."}
            )

        if quantity > available_quantity:
            raise serializers.ValidationError(
                {"detail": "Quantity cannot exceed the available quantity."}
            )

    def validate_amount(self, amount: Decimal, original_price: Decimal) -> None:
        """Validate the amount of the refund line."""
        if amount > original_price:
            raise serializers.ValidationError(
                {"detail": "Amount cannot exceed the original BillableItem price."}
            )


class InvoiceTransitionLogSerializer(BaseSerializer):
    """InvoiceTransitionLog Serializer."""

    class Meta:
        """Serialization options."""

        model = InvoiceTransitionLog
        fields = "__all__"


class InvoiceSerializer(BaseSerializer):
    """Invoice Serializer."""

    sales_invoice_id = serializers.ReadOnlyField()
    invoice_number = serializers.ReadOnlyField()
    workflow_state = serializers.ReadOnlyField()
    invoice_lines = BillableItemSerializer(read_only=True, many=True)
    payments = PaymentSerializer(read_only=True, many=True)
    amount_due = serializers.ReadOnlyField()
    amount_paid = serializers.ReadOnlyField()
    refunds = RefundSerializer(read_only=True, many=True)
    refund_status = serializers.ReadOnlyField()

    class Meta:
        """Serialization options."""

        model = Invoice
        fields = "__all__"
