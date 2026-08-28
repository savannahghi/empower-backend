"""Billing tasks."""
import logging
import uuid

from django.conf import settings

from sil_advantage.billing.models import Payment, Refund
from sil_advantage.common.api_clients import get_erp_client
from sil_advantage.common.api_clients.erp import fetch_from_erp_cache
from sil_advantage.common.tasks import BaseTaskWithRetry
from sil_advantage.config import celery_app
from sil_advantage.integrations.tasks import sync_updates_to_remote

LOGGER = logging.getLogger(__name__)


@celery_app.task(base=BaseTaskWithRetry)
def send_billing_event_to_erp(
    service: str,
    billing_code: str,
    value: int,
    wallet: str,
    transaction_id: uuid.UUID,
    timestamp: str,
    workstation_id: uuid.UUID,
    customer_id: uuid.UUID,
    branch_id: uuid.UUID,
) -> None:
    """Send a billing event to the ERP."""
    erp = get_erp_client(workstation_id)
    sil_org = fetch_from_erp_cache(
        "organisations",
        "get_with",
        filter={
            "slade_code": settings.TRANSACTING_SIL_ORG_SLADE_CODE,
        },
    )
    erp.billing_events.create(
        {
            "organisation": sil_org["id"],
            "service": service,
            "billing_code": billing_code,
            "value": value,
            "wallet": wallet,
            "external_id": transaction_id,
            "timestamp": timestamp,
            "customer": customer_id,
            "branch": branch_id,
        }
    )


def process_refund_on_erp(refund_id: uuid.UUID) -> None:
    """Processing refunds on ERP."""
    try:
        refund = Refund.objects.get(id=refund_id)
        sync_updates_to_remote(
            "billing.refund",
            refund.id,
            "ERP",
            "CREATE",
        )
        refund.refresh_from_db()

        for line in refund.refund_lines.only("id"):
            sync_updates_to_remote(
                "billing.refundline",
                line.id,
                "ERP",
                "CREATE",
            )

        erp = get_erp_client(refund.workstation_id)
        erp.sales_credit_notes.transition(
            refund.sales_credit_note_id,
            "DRAFT_SUBMIT_APPROVE",
        )

        existing_payment = refund.invoice.payments.first()
        if not existing_payment:
            return None

        visit = refund.invoice.service_request.visit
        receipt = erp.payment_receipts.create(
            {
                "amount": (-1 * refund.amount),
                "source_organisation_unit": str(refund.department_id),
                "organisation": str(refund.organisation_id),
                "business_partner": (visit.customer_id or visit.patient.customer_id),
                "payment_method": existing_payment.payment_method,
                "currency": existing_payment.currency,
                "source": "CUSTOMER",
                "payment_date": refund.created,
                "source_document": refund.invoice.sales_invoice_id,
                "workflow_state": "DRAFT",
                "created_by": refund.updated_by,
                "updated_by": refund.updated_by,
            }
        )
        payment = Payment.objects.create(
            invoice=refund.invoice,
            payment_receipt_id=receipt["id"],
            payment_method=receipt["payment_method"],
            currency=receipt["currency"],
            amount=receipt["amount"],
            payment_date=receipt["payment_date"],
            organisation=refund.organisation,
            branch_id=refund.branch_id,
            department_id=refund.department_id,
            workstation_id=refund.workstation_id,
            created_by=refund.updated_by,
            updated_by=refund.updated_by,
        )
        erp.payment_receipts.transition(
            payment.payment_receipt_id,
            "DRAFT_SUBMIT_APPROVE",
        )
    except Exception as exc:
        LOGGER.error(f"Failed to process refund {refund_id}: {exc}", exc_info=True)
        raise
