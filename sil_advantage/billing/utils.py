"""Billing utilities."""
import logging
from decimal import Decimal
from typing import Dict, List, Optional

from django.db import models
from django.utils import timezone
from sil_erp_client import ERP

from sil_advantage.billing import serializers
from sil_advantage.billing.models import (
    BillableItem,
    Invoice,
    Payment,
    Refund,
    RefundLine,
)
from sil_advantage.common.api_clients.erp import erp_configured, get_erp_client
from sil_advantage.common.cache import cached
from sil_advantage.common.models import Organisation
from sil_advantage.common.types import AuthenticatedRequest

LOGGER = logging.getLogger(__file__)

"""Wallets."""


@cached(ttl=600)
def get_wallet_balances(org: Organisation, branch_id: Optional[str] = None) -> dict:
    """Get wallet balances."""
    if not erp_configured():
        return {}

    erp = get_erp_client(None)
    filters = {
        "_identifiers": "bulk_sms_account",
        "customer": org.customer_id,
    }
    if branch_id:
        filters["branch"] = branch_id
    accounts = erp.account_balances.list(filters=filters)

    wallets = {}
    for account in accounts["results"]:
        wallets[account["_identifiers"]] = {
            "type": account["_identifiers"],
            "balance": Decimal(account["balance"]),
        }
    return wallets


def process_payment_for_invoice(
    request: AuthenticatedRequest, invoice: Invoice, data: dict, erp: ERP
) -> dict:
    """Process payment for a single invoice."""
    if invoice.sales_invoice_id is None:
        raise ValueError(
            "The invoice does not have a sales invoice ID."
            " Payment cannot be processed without it."
        )
    data["invoice"] = invoice.pk
    user = request.user
    serializer = serializers.PaymentSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    payload = serializer.data

    payload["payment_date"] = (
        timezone.now().replace(second=0, microsecond=0).isoformat()
    )

    visit = invoice.service_request.visit
    receipt = erp.payment_receipts.create(
        {
            "amount": payload["amount"],
            "source_organisation_unit": str(invoice.department_id),
            "organisation": str(invoice.organisation_id),
            "business_partner": visit.guarantor_id or visit.patient.customer_id,
            "payment_method": payload["payment_method"],
            "currency": payload["currency"],
            "source": "CUSTOMER",
            "payment_date": payload["payment_date"],
            "reference_number": payload["payment_reference"],
            "source_document": invoice.sales_invoice_id,
            "workflow_state": "DRAFT",
            "created_by": user.guid,
            "updated_by": user.guid,
        }
    )
    allocate = str(
        round(min(invoice.amount_due, Decimal(receipt["amount"])), 4),
    )
    result = erp.customer_invoice_payments.create(
        {
            "amount": allocate,
            "invoice": invoice.sales_invoice_id,
            "payment": receipt["id"],
            "organisation": str(invoice.organisation_id),
            "created_by": user.guid,
            "updated_by": user.guid,
        }
    )
    payment = Payment.objects.create(
        invoice=invoice,
        payment_receipt_id=receipt["id"],
        payment_method=payload["payment_method"],
        payment_method_name=payload["payment_method_name"],
        currency=payload["currency"],
        amount=payload["amount"],
        payment_date=payload["payment_date"],
        payment_reference=payload["payment_reference"],
        organisation=invoice.organisation,
        created_by=user.guid,
        updated_by=user.guid,
        branch_id=invoice.branch_id,
        department_id=invoice.department_id,
        workstation_id=invoice.workstation_id,
    )

    payment.customer_invoice_payment_id = result["id"]
    payment.save(update_fields=["customer_invoice_payment_id"])

    visit = invoice.service_request.visit
    if visit.status in ("ARRIVED", "TRIAGED"):
        visit.status = "IN_PROGRESS"
        visit.save(update_fields=["status"])

    data = serializers.PaymentSerializer(payment).data
    return data


def get_refundable_invoice_lines(
    invoice: Invoice,
    context: Dict[str, object],
    refund: Refund,
    invoice_lines: models.QuerySet[BillableItem],
) -> List[RefundLine]:
    """Check partially refunded invoice and get refund lines for next full refund."""
    refundable_lines = []

    for line in invoice_lines:
        corresponding_refund_line = line.refund_line.first()

        if not corresponding_refund_line:
            refund_line = RefundLine(
                refund=refund,
                invoice_line=line,
                quantity=line.quantity,
                amount=line.price,
                **context,
            )
            refundable_lines.append(refund_line)
        else:
            remaining_quantity = line.quantity - corresponding_refund_line.quantity
            if remaining_quantity > 0:
                refundable_lines.append(
                    RefundLine(
                        refund=refund,
                        invoice_line=line,
                        quantity=remaining_quantity,
                        amount=corresponding_refund_line.amount,
                        **context,
                    )
                )

            remaining_amount = line.price - (
                corresponding_refund_line.amount or Decimal("0")
            )
            if remaining_amount > 0:
                refundable_lines.append(
                    RefundLine(
                        refund=refund,
                        invoice_line=line,
                        quantity=corresponding_refund_line.quantity,
                        amount=remaining_amount,
                        **context,
                    )
                )

    return refundable_lines
