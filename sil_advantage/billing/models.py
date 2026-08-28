"""Billing models."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, Sequence
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Sum
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from sil_cacheable.orm import CacheableManager

from sil_advantage.billing import (
    FULLY_REFUNDED,
    NOT_REFUNDED,
    PARTIALLY_REFUNDED,
    REFUND_REASONS,
)
from sil_advantage.common.models import (
    AbstractBase,
    OrgUnitIdsMixin,
    TransitionValidationMixin,
)
from sil_advantage.common.utilities.misc import round_off_monetary_value
from sil_advantage.integrations.mixins import RemoteObjectMixin
from sil_advantage.visits.models import ServiceRequest

ERP_DOCUMENT_WORKFLOW_STATES = (
    ("DRAFT", "Editable by document creator."),
    ("SUBMITTED", "Submitted for review by approver(s)"),
    ("RETURNED", "Returned to creator to make corretions."),
    ("PROCESSED", "Been approved and accounting entries made."),
    ("REJECTED", "Rejected by approver(s)"),
    ("INVALIDATED", "Cancelled for editing in a new document."),
    ("ARCHIVED", "Closed for an processed document."),
    ("CLOSED", "Closed for a document that is not processed."),
)

PAYMENT_TYPE_CHOICES = (
    (
        "SELF_PAY",
        "To be paid by patient to cover for costs not undertaken by the guarantor",
    ),
    ("COPAY", "To be paid by patient as obligation requested from the guarantor"),
)
ERP_DOCUMENT_WORKFLOW_TRANSITION_GRAPH = {
    "DRAFT": ["SUBMITTED", "CLOSED"],
    "SUBMITTED": ["PROCESSED", "RETURNED", "REJECTED", "CLOSED"],
    "RETURNED": ["SUBMITTED", "CLOSED"],
    "PROCESSED": ["INVALIDATED", "ARCHIVED"],
    "REJECTED": ["CLOSED"],
    "INVALIDATED": ["CLOSED"],
    "ARCHIVED": [],
    "CLOSED": [],
}
logger = logging.getLogger(__name__)


def check_stock_quantity(item: "BillableItem") -> Dict[str, Any]:
    """Check the stock quantity of an item in ERP."""
    from sil_advantage.common.api_clients.erp import get_erp_client

    try:
        erp = get_erp_client(None)
        filters = {
            "product_id": item.product_id,
            "department_id": item.department_id,
        }
        response = erp.stockquantity.check_stock_quantity(**filters)
        stock_quantity_exists = response.get("stock_quantity_exists")
        available_quantity = response.get("quantity", 0)
        return {
            "stock_quantity_exists": stock_quantity_exists,
            "available_quantity": available_quantity,
        }
    except Exception as e:
        logger.error(
            f"Failed to check stock quantity for product {item.product_id}: {e}"
        )
        return {
            "stock_quantity_exists": False,
            "available_quantity": 0,
        }


class ClinicalOrderTransitionLog(OrgUnitIdsMixin, AbstractBase):
    """Hold clinical order state transition logs."""

    clinical_order = models.ForeignKey(
        "ClinicalOrder",
        on_delete=models.CASCADE,
        related_name="state_transition_logs",
    )
    workflow_state = models.CharField(
        max_length=20,
        choices=ERP_DOCUMENT_WORKFLOW_STATES,
    )
    workflow_state_from = models.CharField(
        max_length=20,
        choices=ERP_DOCUMENT_WORKFLOW_STATES,
    )
    workflow_state_to = models.CharField(
        max_length=20,
        choices=ERP_DOCUMENT_WORKFLOW_STATES,
    )

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass


class ClinicalOrder(  # type: ignore
    RemoteObjectMixin,
    TransitionValidationMixin,
    OrgUnitIdsMixin,
    AbstractBase,
):
    """Hold information on clinical orders.

    Sales order lines can be: prescriptions, lab tests, etc.
    """

    service_request = models.OneToOneField(
        ServiceRequest,
        on_delete=models.PROTECT,
        related_name="clinical_order",
    )

    # ID of the equivalent SalesOrder on the ERP
    sales_order_id = models.UUIDField(unique=True, null=True, blank=True)
    # Sales Order Number of the SalesOrder on the ERP
    sales_order_number = models.CharField(max_length=255, null=True, blank=True)
    # Workflow state of the equivalent SalesOrder on the ERP
    workflow_state = models.CharField(
        choices=ERP_DOCUMENT_WORKFLOW_STATES,
        max_length=255,
        default="DRAFT",
    )

    _remote_obj_refs = {
        "ERP": [
            (
                "sales_orders",
                {
                    "sales_order_id": "id",
                    "workflow_state": "workflow_state",
                    "sales_order_number": "document_number",
                },
            ),
        ],
    }

    _transition_graph = ERP_DOCUMENT_WORKFLOW_TRANSITION_GRAPH
    _transition_field = "workflow_state"
    _transition_log_model = ClinicalOrderTransitionLog
    _transition_log_model_fk_field = "clinical_order"

    model_validators = []
    organisation_verify = ["service_request"]

    objects: models.Manager["ClinicalOrder"] = CacheableManager()
    _related_serialized_models = ("billing_billableitem",)

    # eager = cls.select_related()

    class Meta(AbstractBase.Meta):
        """Set model options."""

        unique_together = [["organisation", "sales_order_number"]]

    @property
    def erp_sales_orders_payload(self) -> dict[str, str | Optional[UUID]]:
        """ERP sales order payload."""
        visit = self.service_request.visit
        return {
            "customer": str(visit.customer_id or visit.patient.customer_id),
            "source_organisation_unit": str(self.department_id),
            "organisation": str(self.organisation_id),
            "workflow_state": self.workflow_state,
        }


class InvoiceTransitionLog(OrgUnitIdsMixin, AbstractBase):
    """Hold invoice state transition logs."""

    invoice = models.ForeignKey(
        "Invoice",
        on_delete=models.CASCADE,
        related_name="state_transition_logs",
    )
    workflow_state = models.CharField(
        max_length=20, choices=ERP_DOCUMENT_WORKFLOW_STATES
    )
    workflow_state_from = models.CharField(
        max_length=20, choices=ERP_DOCUMENT_WORKFLOW_STATES
    )
    workflow_state_to = models.CharField(
        max_length=20, choices=ERP_DOCUMENT_WORKFLOW_STATES
    )

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass


class Invoice(  # type: ignore
    RemoteObjectMixin,
    TransitionValidationMixin,
    OrgUnitIdsMixin,
    AbstractBase,
):
    """Thin wrapper around the ERP SalesInvoice."""

    invoice_lines: models.QuerySet["BillableItem"]
    payments: models.QuerySet["Payment"]
    refunds: models.QuerySet["Refund"]

    service_request = models.OneToOneField(
        ServiceRequest,
        on_delete=models.PROTECT,
        related_name="invoice",
    )

    # ID of the SalesInvoice on the ERP
    sales_invoice_id = models.UUIDField(unique=True, null=True, blank=True)
    # Invoice Number of the SalesInvoice on the ERP
    invoice_number = models.CharField(max_length=255, null=True, blank=True)
    # Workflow state of the equivalent SalesOrder on the ERP
    workflow_state = models.CharField(
        choices=ERP_DOCUMENT_WORKFLOW_STATES,
        max_length=255,
        default="DRAFT",
    )

    _remote_obj_refs = {
        "ERP": [
            (
                "sales_invoices",
                {
                    "sales_invoice_id": "id",
                    "invoice_number": "document_number",
                    "workflow_state": "workflow_state",
                },
            ),
        ],
    }

    _transition_graph = ERP_DOCUMENT_WORKFLOW_TRANSITION_GRAPH
    _transition_field = "workflow_state"
    _transition_log_model = InvoiceTransitionLog
    _transition_log_model_fk_field = "invoice"

    model_validators: Sequence[str] = []
    organisation_verify = ["service_request"]

    objects: models.Manager["Invoice"] = CacheableManager()
    _related_serialized_models = (
        "billing_refund",
        "billing_payment",
        "billing_billableitem",
    )

    class Meta(AbstractBase.Meta):
        """Set model options."""

        unique_together = [["organisation", "invoice_number"]]

    @property
    def erp_sales_invoices_payload(
        self,
    ) -> dict[str, str | Optional[UUID] | datetime]:
        """ERP sales invoice payload."""
        first_payment = self.payments.first()
        return {
            "invoice_date": self.service_request.visit.start,
            "customer": str(self.service_request.visit.guarantor_id)
            if self.service_request.visit.guarantor_id
            else str(self.service_request.visit.patient.customer_id),
            "secondary_customer": str(self.service_request.visit.patient.customer_id),
            "sales_type": str(self.service_request.visit.billing_class).lower(),
            "source_organisation_unit": str(self.department_id),
            "organisation": str(self.organisation_id),
            "workflow_state": self.workflow_state,
            "currency": first_payment.currency if first_payment else None,
            "payment_method": first_payment.payment_method if first_payment else None,
        }

    @cached_property
    def amount_due(self) -> Decimal:
        """Calculate the amount due for this invoice."""
        amount_due = Decimal("0")
        for line in self.invoice_lines.all():
            amount_due += line.price * line.quantity
        return amount_due

    @cached_property
    def amount_paid(self) -> Decimal:
        """Calculate the total amount of payments."""
        amount_paid = Decimal("0")
        for payment in self.payments.all():
            amount_paid += payment.amount
        return amount_paid

    @property
    def refund_status(self) -> str:
        """Determine if the invoice is partially or fully refunded."""
        refunds = self.refunds.all()
        if not refunds:
            return NOT_REFUNDED

        refunded_amount = Decimal("0")
        for refund in refunds:
            refunded_amount += refund.refund_amount

        if refunded_amount < self.amount_due:
            return PARTIALLY_REFUNDED
        else:
            return FULLY_REFUNDED


class PaymentTransitionLog(OrgUnitIdsMixin, AbstractBase):
    """Hold payment state transition logs."""

    payment = models.ForeignKey(
        "Payment",
        on_delete=models.CASCADE,
        related_name="state_transition_logs",
    )
    workflow_state = models.CharField(
        max_length=20, choices=ERP_DOCUMENT_WORKFLOW_STATES
    )
    workflow_state_from = models.CharField(
        max_length=20, choices=ERP_DOCUMENT_WORKFLOW_STATES
    )
    workflow_state_to = models.CharField(
        max_length=20, choices=ERP_DOCUMENT_WORKFLOW_STATES
    )

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass


class Payment(
    OrgUnitIdsMixin,
    AbstractBase,
):
    """Thin wrapper around ERP payments."""

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    payment_method = models.UUIDField(null=True, blank=True)
    payment_type = models.CharField(
        max_length=20, choices=PAYMENT_TYPE_CHOICES, null=True, blank=True
    )
    payment_method_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )
    currency = models.UUIDField(null=True, blank=True)
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=settings.DECIMAL_PLACES,
    )
    payment_date = models.DateTimeField(default=timezone.now)
    payment_reference = models.CharField(
        max_length=64,
        null=True,
        blank=True,
    )

    # ID on the ERP
    payment_receipt_id = models.UUIDField(unique=True)
    # Workflow state of the equivalent Payment Receipt on the ERP
    workflow_state = models.CharField(
        choices=ERP_DOCUMENT_WORKFLOW_STATES,
        max_length=255,
        default="DRAFT",
    )
    customer_invoice_payment_id = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
    )

    _transition_graph = ERP_DOCUMENT_WORKFLOW_TRANSITION_GRAPH
    _transition_field = "workflow_state"
    _transition_log_model = PaymentTransitionLog
    _transition_log_model_fk_field = "payment"

    organisation_verify = ["invoice"]

    objects: models.Manager["Payment"] = CacheableManager()

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass


class BillableItem(RemoteObjectMixin, OrgUnitIdsMixin, AbstractBase):  # type: ignore
    """Hold information on billed items.

    Billing is a two step process:
        We first add the items to a sales order on the ERP
        where we can freely update the items.
        Next, these are added to the invoice where no more edits can be made.
    """

    clinical_order = models.ForeignKey(
        ClinicalOrder,
        on_delete=models.PROTECT,
        related_name="order_lines",
        null=True,
        blank=True,
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="invoice_lines",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(1)],
    )

    # ID of the Product on the ERP
    product_id = models.UUIDField()
    pricelist_product_id = models.UUIDField()
    # ID of the SalesOrderLine on the ERP
    sales_order_line_id = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
    )
    # ID of the SalesInvoiceLine on the ERP
    sales_invoice_line_id = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
    )
    # Actual selling price (with discounts)
    price = models.DecimalField(
        max_digits=20,
        decimal_places=settings.DECIMAL_PLACES,
    )
    # Price on the ERP
    original_price = models.DecimalField(
        max_digits=20,
        decimal_places=settings.DECIMAL_PLACES,
    )

    # Tax code on ERP
    tax_rate = models.CharField(
        null=True,
        blank=True,
    )

    _remote_obj_refs = {
        "ERP": [
            (
                "sales_invoice_lines",
                {
                    "sales_invoice_line_id": "id",
                    "price": "new_price",
                    "tax_rate": "tax_code_description",
                },
            ),
            (
                "sales_order_lines",
                {
                    "sales_order_line_id": "id",
                },
            ),
        ],
    }

    organisation_verify = ["clinical_order", "invoice"]
    model_validators = [
        "validate_order_or_invoice_provided",
        "validate_quantity_is_not_more_than_stock_quantity",
    ]

    objects: models.Manager["BillableItem"] = CacheableManager()

    class Meta(AbstractBase.Meta):
        """Set model options."""

        ordering = ("updated", "created")

    def validate_order_or_invoice_provided(self) -> None:
        """Validate that an order or an invoice has been provided."""
        if not (self.invoice or self.clinical_order):
            raise ValidationError(
                _(
                    "A billable item must be linked to "
                    "a clinical order and/or an invoice."
                )
            )

    def validate_quantity_is_not_more_than_stock_quantity(self) -> None:
        """Validate that the quantity is not more than the stock quantity on ERP."""
        if not self.department_id:
            # Exit the function if the department ID is not provided
            # TODO: retrun a validation error
            return

        stock = check_stock_quantity(self)
        if not stock["stock_quantity_exists"]:
            return

        if stock["available_quantity"] < self.quantity:
            raise ValidationError(
                f"Not enough stock for the product {self.name}. "
                f"Available: {stock['available_quantity']}, required: {self.quantity}."
            )

    @property
    def erp_sales_invoice_lines_payload(
        self,
    ) -> Optional[dict[str, Optional[str | UUID | Decimal]]]:
        """ERP sales invoice lines payload."""
        if self.invoice is None:
            return None

        return {
            "sales_invoice": str(self.invoice.sales_invoice_id),
            "sales_order_line": self.sales_order_line_id,
            "quantity": self.quantity,
            "product": str(self.product_id),
            "pricelist_product": str(self.pricelist_product_id),
            "new_price": self.price,
            "source_document": self.sales_order_line_id,
            "organisation": str(self.organisation_id),
        }

    @property
    def erp_sales_order_lines_payload(
        self,
    ) -> Optional[dict[str, Optional[str | UUID | Decimal]]]:
        """ERP sales order lines payload."""
        if self.clinical_order is None:
            return None
        stock = check_stock_quantity(self)
        if not stock["stock_quantity_exists"]:
            return None
        return {
            "sales_order": self.clinical_order.sales_order_id,
            "quantity": self.quantity,
            "product": str(self.product_id),
            "new_price": self.price,
            "organisation": str(self.organisation_id),
            "quantity_confirmed": self.quantity,
        }


class RefundTransitionLog(OrgUnitIdsMixin, AbstractBase):
    """Hold refund state transition logs."""

    refund = models.ForeignKey(
        "Refund",
        on_delete=models.CASCADE,
        related_name="state_transition_logs",
    )
    workflow_state = models.CharField(
        max_length=20,
        choices=ERP_DOCUMENT_WORKFLOW_STATES,
    )
    workflow_state_from = models.CharField(
        max_length=20,
        choices=ERP_DOCUMENT_WORKFLOW_STATES,
    )
    workflow_state_to = models.CharField(
        max_length=20,
        choices=ERP_DOCUMENT_WORKFLOW_STATES,
    )

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass


class Refund(  # type: ignore
    RemoteObjectMixin,
    TransitionValidationMixin,
    OrgUnitIdsMixin,
    AbstractBase,
):
    """Thin wrapper around the ERP SalesCreditNote."""

    refund_lines: models.QuerySet["RefundLine"]
    invoice = models.ForeignKey(
        Invoice,
        related_name="refunds",
        on_delete=models.PROTECT,
    )

    # ID of the SalesCreditNote on the ERP
    sales_credit_note_id = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
    )
    # Sales Credit Note Number of the SalesCreditNote on the ERP
    refund_number = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    # Reason of the SalesCreditNote on the ERP
    reason = models.TextField(max_length=255)
    # KRA Refund Reason of the SalesCreditNote on the ERP
    kra_reason_code = models.CharField(
        max_length=255, choices=REFUND_REASONS, null=True, blank=True
    )
    # Workflow state of the equivalent SalesCreditNote on the ERP
    workflow_state = models.CharField(
        choices=ERP_DOCUMENT_WORKFLOW_STATES,
        max_length=255,
        default="DRAFT",
    )

    _remote_obj_refs = {
        "ERP": [
            (
                "sales_credit_notes",
                {
                    "sales_credit_note_id": "id",
                    "refund_number": "document_number",
                    "workflow_state": "workflow_state",
                },
            ),
        ],
    }

    _transition_graph = ERP_DOCUMENT_WORKFLOW_TRANSITION_GRAPH
    _transition_field = "workflow_state"
    _transition_log_model = RefundTransitionLog
    _transition_log_model_fk_field = "refund"

    model_validators: Sequence[str] = [
        "validate_invoice_fully_refunded",
        "validate_invoice_creation_date",
        "validate_invoice_workflow_state",
    ]
    organisation_verify = ["invoice"]

    objects: models.Manager["Refund"] = CacheableManager()

    def validate_invoice_fully_refunded(self) -> None:
        """Validate that the invoice has been fully refunded."""
        if self._state.adding:
            if self.invoice.refund_status == FULLY_REFUNDED:
                raise ValidationError(
                    {"detail": "This invoice has already been fully refunded."}
                )

    def validate_invoice_creation_date(self) -> None:
        """Validate the invoice is not older than 6 months."""
        six_months_ago = timezone.now() - timedelta(days=180)
        if self.invoice.created < six_months_ago:
            raise ValidationError(
                {"detail": "Cannot refund invoices older than 6 months."}
            )

    def validate_invoice_workflow_state(self) -> None:
        """Validate the invoice is in a valid state for refund."""
        if self.invoice.workflow_state not in ["PROCESSED", "ARCHIVED"]:
            raise ValidationError({"detail": "Kindly ensure the invoice is processed."})

    class Meta(AbstractBase.Meta):
        """Set model options."""

        unique_together = [["organisation", "refund_number"]]

    @property
    def erp_sales_credit_notes_payload(self) -> dict[str, str | Optional[UUID]]:
        """ERP sales credit note payload."""
        visit = self.invoice.service_request.visit

        return {
            "customer": str(visit.customer_id or visit.patient.customer_id),
            "reason": self.reason,
            "kra_reason_code": self.kra_reason_code,
            "amount": str(self.amount),
            "invoice": str(self.invoice.sales_invoice_id),
            "source_organisation_unit": str(self.department_id),
            "organisation": str(self.organisation_id),
            "workflow_state": self.workflow_state,
        }

    @property
    def amount(self) -> Decimal:
        """Calculate the total amount for this refund."""
        amount = Decimal("0")
        for line in self.refund_lines.select_related("invoice_line").all():
            amount += line.invoice_line.price * line.invoice_line.quantity
        return round_off_monetary_value(amount)

    @property
    def refund_amount(self) -> Decimal:
        """Calculate the total amount for this refund."""
        refunded_amount = self.refund_lines.all().aggregate(
            total=Sum(F("amount") * F("quantity"))
        )["total"] or Decimal("0")
        return round_off_monetary_value(refunded_amount)


class RefundLine(RemoteObjectMixin, OrgUnitIdsMixin, AbstractBase):  # type: ignore
    """Hold information on refundable items."""

    refund = models.ForeignKey(
        Refund,
        on_delete=models.PROTECT,
        related_name="refund_lines",
    )
    invoice_line = models.ForeignKey(
        BillableItem,
        on_delete=models.PROTECT,
        related_name="refund_line",
    )

    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(1)],
    )
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
    )

    sales_credit_note_line_id = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
    )

    _remote_obj_refs = {
        "ERP": [
            (
                "sales_credit_note_lines",
                {
                    "sales_credit_note_line_id": "id",
                },
            ),
        ],
    }

    organisation_verify = ["refund"]

    objects: models.Manager["RefundLine"] = CacheableManager()

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass

    @property
    def erp_sales_credit_note_lines_payload(
        self,
    ) -> Optional[dict[str, Optional[str | UUID | Decimal]]]:
        """ERP sales credit note lines payload."""
        return {
            "credit_note": str(self.refund.sales_credit_note_id),
            "quantity": self.quantity,
            "product": str(self.invoice_line.product_id),
            "pricelist_product": str(self.invoice_line.pricelist_product_id),
            "new_price": self.amount,
            "organisation": str(self.organisation_id),
        }
