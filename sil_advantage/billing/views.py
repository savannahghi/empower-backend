"""Billing views."""
import logging
from decimal import Decimal
from typing import Sequence
from uuid import UUID

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import UpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_204_NO_CONTENT
from rest_framework.views import APIView
from sil_transitions.views import TransitionViewMixin

from sil_advantage.billing import filters, models, serializers, tasks, utils
from sil_advantage.common.api_clients.erp import get_erp_client
from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.common.views.base import CacheableBaseView
from sil_advantage.permissions import perms, scopes
from sil_advantage.sil_auth.permission_classes import (
    OrganisationIsActive,
    ViewBasePermission,
)

LOGGER = logging.getLogger(__name__)


class ClinicalOrderViewSet(CacheableBaseView):
    """Viewset for ClinicalOrders."""

    permissions = {
        "GET": [perms.ORDER_VIEW],
        "POST": [perms.ORDER_CREATE],
        "PATCH": [perms.ORDER_EDIT],
        "DELETE": [perms.ORDER_DELETE],
    }
    scopes = {
        "GET": [scopes.ORDER_READ],
        "POST": [scopes.ORDER_WRITE],
        "PATCH": [scopes.ORDER_WRITE],
        "DELETE": [scopes.ORDER_WRITE],
    }
    queryset = models.ClinicalOrder.objects.all().prefetch_related("order_lines")
    serializer_class = serializers.ClinicalOrderSerializer
    filterset_class = filters.ClinicalOrderFilter
    ordering_fields = ("updated",)
    search_fields: Sequence[str] = []

    _data_partition_field = "department_id"


class ClinicalOrderTransitionView(TransitionViewMixin, UpdateAPIView):
    """ClinicalOrderTransition API View."""

    permissions = {
        "GET": [perms.ORDER_VIEW],
        "POST": [perms.ORDER_CREATE],
        "PATCH": [perms.ORDER_EDIT],
        "DELETE": [perms.ORDER_DELETE],
    }
    scopes = {
        "GET": [scopes.ORDER_READ],
        "POST": [scopes.ORDER_WRITE],
        "PATCH": [scopes.ORDER_WRITE],
        "DELETE": [scopes.ORDER_WRITE],
    }
    queryset = models.ClinicalOrder.objects.all()
    permission_classes = (IsAuthenticated & ViewBasePermission & OrganisationIsActive,)
    serializer_class = serializers.ClinicalOrderSerializer
    lookup_field = "id"
    transition_graph = models.ERP_DOCUMENT_WORKFLOW_TRANSITION_GRAPH
    transition_field = "workflow_state"
    transition_log_serializer = serializers.ClinicalOrderTransitionLogSerializer

    _data_partition_field = "department_id"


class InvoiceViewSet(CacheableBaseView):
    """Viewset for Invoices."""

    permissions = {
        "GET": [perms.INVOICE_VIEW],
        "POST": [perms.INVOICE_CREATE],
        "PATCH": [perms.INVOICE_EDIT],
        "DELETE": [perms.INVOICE_DELETE],
    }
    scopes = {
        "GET": [scopes.INVOICE_READ],
        "POST": [scopes.INVOICE_WRITE],
        "PATCH": [scopes.INVOICE_WRITE],
        "DELETE": [scopes.INVOICE_WRITE],
    }
    queryset = models.Invoice.objects.all().prefetch_related(
        "invoice_lines",
        "payments",
    )
    _prefetch_related = ["refunds"]
    serializer_class = serializers.InvoiceSerializer
    filterset_class = filters.InvoiceFilter
    ordering_fields = ("updated",)
    search_fields: Sequence[str] = []

    _data_partition_field = "department_id"

    @action(detail=True, methods=["POST"])
    @transaction.atomic
    def record_payment(
        self,
        request: AuthenticatedRequest,
        pk: UUID,
    ) -> Response:
        """Record a payment on the ERP.

        Recording payments on the ERP is a two-step process:
            1. We add a payment receipt
            2. We link the receipt to a sales invoice.

        This endpoint does both actions instead of the
        frontend having to call the ERP twice.
        """
        invoice = models.Invoice.objects.select_related(
            "service_request__visit__patient",
            "organisation",
        ).get(pk=pk)
        erp = get_erp_client(invoice.workstation_id)

        payment_record = utils.process_payment_for_invoice(
            request, invoice, request.data, erp
        )
        return Response(payment_record)

    @action(detail=False, methods=["POST"])
    @transaction.atomic
    def record_multiple_payments(self, request: AuthenticatedRequest) -> Response:
        """Record payments on the ERP for multiple invoices at once."""
        invoice_ids = request.data.get("invoice_ids", [])
        total_amount = Decimal(request.data.get("amount", 0))
        payment_date = request.data.get("payment_date")
        payment_method = request.data.get("payment_method")
        payment_method_name = request.data.get("payment_method_name")
        currency = request.data.get("currency")

        invoices = (
            models.Invoice.objects.select_related(
                "service_request__visit__patient",
                "organisation",
            )
            .filter(pk__in=invoice_ids)
            .order_by("pk")
        )
        if not invoices:
            return Response(
                {"detail": "One or more invoices do not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment_count = 0
        erp = get_erp_client(invoices[0].workstation_id)
        for invoice in invoices:
            # Calculate the amount to pay for this invoice
            amount_to_pay = round(min(invoice.amount_due, total_amount), 4)

            payment_data = {
                "amount": str(amount_to_pay),
                "currency": currency,
                "payment_date": payment_date,
                "payment_method": payment_method,
                "payment_method_name": payment_method_name,
            }

            try:
                # Record payment for the invoice
                utils.process_payment_for_invoice(request, invoice, payment_data, erp)

                # Reduce the total_amount by the amount paid for this invoice
                total_amount -= amount_to_pay

                payment_count += 1

            except Exception as e:
                LOGGER.error(f"An error occurred: {str(e)}")
                return Response(
                    {"detail": "An error occurred while processing payments."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(
            {
                "detail": "Payments recorded successfully.",
                "payment_count": payment_count,
            }
        )

    @action(detail=True, methods=["POST"])
    def refund_payment(self, request: AuthenticatedRequest, pk: UUID) -> Response:
        """Close a draft payment and refund the payment.

        Payload format:
        {
            "payment_receipt_id": "<UUID>",
        }
        """
        invoice: models.Invoice = self.get_object()
        payment_receipt_id = UUID(request.data["payment_receipt_id"])

        payment = invoice.payments.filter(
            payment_receipt_id=payment_receipt_id,
        )
        if not payment.exists():
            raise ValidationError(_("The payment is not part of this invoice."))

        erp = get_erp_client(invoice.workstation_id)
        result = erp.payment_receipts.transition(
            payment_receipt_id,
            "DRAFT_CLOSED",
        )

        payment.delete()

        return Response(result)

    @action(detail=True, methods=["POST"])
    @transaction.atomic
    def refund(self, request: AuthenticatedRequest, pk: UUID) -> Response:
        """Record a refund on ERP.

        Recording refunds on ERP is a three-step process:
            1. We create a sales credit note (Refund)
            2. We link the sales credit note to a sales invoice.
            3. We evoke refund (Sales Credit Note) transition process.

        This endpoint does both actions instead of the
        frontend having to call the ERP twice.
        """
        invoice: models.Invoice = self.get_object()

        serializer = serializers.RefundInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.data

        context = {
            "organisation": invoice.organisation,
            "branch_id": invoice.branch_id,
            "workstation_id": invoice.workstation_id,
            "department_id": invoice.department_id,
            "created_by": invoice.updated_by,
            "updated_by": invoice.updated_by,
        }

        refund = models.Refund(
            invoice=invoice,
            reason=payload["reason"],
            kra_reason_code=payload["kra_reason_code"],
            **context,
        )
        refund._disable_sync = True
        refund.save()

        invoice_lines = invoice.invoice_lines.all()
        if len(payload["invoice_lines"]) > 0:
            invoice_lines = invoice_lines.filter(
                id__in=payload["invoice_lines"],
            )

        refundable_lines = utils.get_refundable_invoice_lines(
            invoice, context, refund, invoice_lines
        )

        models.RefundLine.objects.bulk_create(refundable_lines)

        tasks.process_refund_on_erp(refund.id)
        data = serializers.RefundSerializer(refund).data
        return Response(data)

    @action(detail=True, methods=["POST"])
    @transaction.atomic
    def refund_line(self, request: AuthenticatedRequest, pk: UUID) -> Response:
        """Record a refund line on ERP."""
        invoice: models.Invoice = self.get_object()

        refund_exist = models.Refund.objects.filter(invoice=invoice).exists()
        if refund_exist:
            raise ValidationError(_("This invoice line has an applied refund to it."))
        serializer = serializers.RefundLineInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        context = {
            "organisation": invoice.organisation,
            "branch_id": invoice.branch_id,
            "workstation_id": invoice.workstation_id,
            "department_id": invoice.department_id,
            "created_by": invoice.updated_by,
            "updated_by": invoice.updated_by,
        }
        refund = models.Refund(
            invoice=invoice,
            reason=payload["reason"],
            kra_reason_code=payload["kra_reason_code"],
            **context,
        )
        refund._disable_sync = True
        refund.save()

        invoice_lines_data = payload["invoice_lines"]
        refund_lines = []

        for line in invoice_lines_data:
            invoice_line = models.BillableItem.objects.get(id=line["id"])

            refund_line = models.RefundLine(
                refund=refund,
                invoice_line=invoice_line,
                quantity=line["quantity"],
                amount=line["amount"],
                **context,
            )
            refund_lines.append(refund_line)
        models.RefundLine.objects.bulk_create(refund_lines)

        tasks.process_refund_on_erp(refund.id)
        data = serializers.RefundSerializer(refund).data
        return Response(data)


class InvoiceTransitionView(TransitionViewMixin, UpdateAPIView):
    """InvoiceTransition API View."""

    permissions = {
        "GET": [perms.INVOICE_VIEW],
        "POST": [perms.INVOICE_CREATE],
        "PATCH": [perms.INVOICE_EDIT],
        "DELETE": [perms.INVOICE_DELETE],
    }
    scopes = {
        "GET": [scopes.INVOICE_READ],
        "POST": [scopes.INVOICE_WRITE],
        "PATCH": [scopes.INVOICE_WRITE],
        "DELETE": [scopes.INVOICE_WRITE],
    }
    queryset = models.Invoice.objects.all()
    permission_classes = (IsAuthenticated & ViewBasePermission & OrganisationIsActive,)
    serializer_class = serializers.InvoiceSerializer
    lookup_field = "id"
    transition_graph = models.ERP_DOCUMENT_WORKFLOW_TRANSITION_GRAPH
    transition_field = "workflow_state"
    transition_log_serializer = serializers.InvoiceTransitionLogSerializer

    _data_partition_field = "department_id"


class PaymentViewSet(CacheableBaseView):
    """Viewset for Payments."""

    permissions = {
        "GET": [perms.INVOICE_VIEW],
        "POST": [perms.INVOICE_CREATE],
        "PATCH": [perms.INVOICE_EDIT],
        "DELETE": [perms.INVOICE_DELETE],
    }
    scopes = {
        "GET": [scopes.INVOICE_READ],
        "POST": [scopes.INVOICE_WRITE],
        "PATCH": [scopes.INVOICE_WRITE],
        "DELETE": [scopes.INVOICE_WRITE],
    }
    queryset = models.Payment.objects.all()
    serializer_class = serializers.PaymentSerializer
    filterset_class = filters.PaymentFilter
    ordering_fields = ("updated",)
    search_fields: Sequence[str] = []

    _data_partition_field = "department_id"


class BillableItemViewSet(CacheableBaseView):
    """Viewset for BillableItems."""

    permissions = {
        "GET": [perms.BILLED_ITEM_VIEW],
        "POST": [perms.BILLED_ITEM_CREATE],
        "PATCH": [perms.BILLED_ITEM_EDIT],
        "DELETE": [perms.BILLED_ITEM_DELETE],
    }
    scopes = {
        "GET": [scopes.BILLED_ITEM_READ],
        "POST": [scopes.BILLED_ITEM_WRITE],
        "PATCH": [scopes.BILLED_ITEM_WRITE],
        "DELETE": [scopes.BILLED_ITEM_WRITE],
    }
    queryset = models.BillableItem.objects.all()
    serializer_class = serializers.BillableItemSerializer
    filterset_class = filters.BillableItemFilter
    ordering_fields = ("updated",)
    search_fields: Sequence[str] = []

    _data_partition_field = "department_id"


class RefundTransitionView(TransitionViewMixin, UpdateAPIView):
    """RefundTransition API View."""

    permissions = {
        "GET": [perms.REFUND_VIEW],
        "POST": [perms.REFUND_CREATE],
        "PATCH": [perms.REFUND_EDIT],
        "DELETE": [perms.REFUND_DELETE],
    }

    scopes = {
        "GET": [scopes.REFUND_READ],
        "POST": [scopes.REFUND_WRITE],
        "PATCH": [scopes.REFUND_WRITE],
        "DELETE": [scopes.REFUND_WRITE],
    }

    queryset = models.Refund.objects.all()
    permission_classes = (IsAuthenticated & ViewBasePermission & OrganisationIsActive,)
    serializer_class = serializers.RefundSerializer
    lookup_field = "id"
    transition_graph = models.ERP_DOCUMENT_WORKFLOW_TRANSITION_GRAPH
    transition_field = "workflow_state"
    transition_log_serializer = serializers.RefundTransitionLogSerializer

    _data_partition_field = "department_id"


class RefundViewSet(CacheableBaseView):
    """Viewset for Refund."""

    permissions = {
        "GET": [perms.REFUND_VIEW],
        "POST": [perms.REFUND_CREATE],
        "PATCH": [perms.REFUND_EDIT],
        "DELETE": [perms.REFUND_DELETE],
    }

    scopes = {
        "GET": [scopes.REFUND_READ],
        "POST": [scopes.REFUND_WRITE],
        "PATCH": [scopes.REFUND_WRITE],
        "DELETE": [scopes.REFUND_WRITE],
    }

    queryset = models.Refund.objects.all().prefetch_related("refund_lines")
    serializer_class = serializers.RefundSerializer
    filterset_class = filters.RefundFilter
    ordering_fields = ("updated",)
    search_fields: Sequence[str] = []

    _data_partition_field = "department_id"


class RefundLineViewSet(CacheableBaseView):
    """Viewset for RefundLine."""

    permissions = {
        "GET": [perms.REFUND_LINE_VIEW],
        "POST": [perms.REFUND_LINE_CREATE],
        "PATCH": [perms.REFUND_LINE_EDIT],
        "DELETE": [perms.REFUND_LINE_DELETE],
    }

    scopes = {
        "GET": [scopes.REFUND_LINE_READ],
        "POST": [scopes.REFUND_LINE_WRITE],
        "PATCH": [scopes.REFUND_LINE_WRITE],
        "DELETE": [scopes.REFUND_LINE_WRITE],
    }

    queryset = models.RefundLine.objects.all()
    serializer_class = serializers.RefundLineSerializer
    filterset_class = filters.RefundLineFilter
    ordering_fields = ("updated",)
    search_fields: Sequence[str] = []

    _data_partition_field = "department_id"


class WalletsView(APIView):
    """Wallets view."""

    permission_classes = (IsAuthenticated,)
    filter_backends: Sequence[str] = []
    search_fields: Sequence[str] = []

    def get(self, request: AuthenticatedRequest) -> Response:
        """List the organization's wallets."""
        org = request.user.organisation
        branch_id = request.META.get("HTTP_X_BRANCH") or request.META.get("X-Branch")
        balances = utils.get_wallet_balances(org, branch_id)

        if not balances:
            return Response(
                data={"message": "No wallets found"}, status=HTTP_204_NO_CONTENT
            )

        return Response(data=balances, status=HTTP_200_OK)
