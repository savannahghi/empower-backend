"""Test billing views."""
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import UUID

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker
from rest_framework import status
from rest_framework.exceptions import ErrorDetail

from sil_advantage.billing import (
    FULLY_REFUNDED,
    PARTIALLY_REFUNDED,
    tasks,
    utils,
)
from sil_advantage.billing.models import (
    BillableItem,
    Invoice,
    Payment,
    Refund,
    RefundLine,
)
from sil_advantage.patients.models import Patient
from sil_advantage.sil_auth.models import SILUser
from sil_advantage.visits.models import Queue, ServiceRequest, Visit
from tests.common.test_common_views import LoggedInMixin

MOCK_ROOT = "sil_advantage.billing.views."
MOCK_TASKS_ROOT = "sil_advantage.billing.tasks."


class InvoiceViewSetTestCase(LoggedInMixin):
    """Test Invoice View."""

    def setUp(self):
        """Set up the test environment."""
        super().setUp()
        baker.make(SILUser, email="network.admin@slade360.co.ke")

        self.ids_metadata = {
            "created_by": self.user.id,
            "updated_by": self.user.id,
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }
        self.patient = baker.make(
            Patient,
            customer_id="1537169c-0716-4e0a-a71e-20d817c08a52",
            **self.ids_metadata,
        )
        self.queue = baker.make(Queue, **self.ids_metadata)
        self.visit = baker.make(
            Visit,
            status="ARRIVED",
            patient=self.patient,
            current_queue=self.queue,
            **self.ids_metadata,
        )

    def extra_headers(self):
        """Workstation headers."""
        return {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_create_billable_items_with_clinical_order(self, mock_create_erp_login):
        """Test creating billable items."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }
        patient = baker.make(
            Patient,
            customer_id="e9fe2c6a-d60d-4722-a3c3-760e9c37b8ec",
            **self.ids_metadata,
        )
        queue = baker.make(Queue)
        baker.make(
            Visit,
            patient=patient,
            current_queue=queue,
            status="ARRIVED",
            **self.ids_metadata,
        )
        service_request = ServiceRequest.objects.latest("created")
        invoice = service_request.invoice
        clinical_order = service_request.clinical_order
        billable_item_data = {
            "product_id": "a1a8a97f-1a6a-4c7d-a64f-007f3ef75072",
            "pricelist_product_id": "fdd90a71-3ebe-444c-9a52-9aa79300a07b",
            "invoice": invoice.id,
            "name": "panadol",
            "clinical_order": clinical_order.id,
            "quantity": 2,
            "price": 2000,
            "original_price": 2000,
        }

        url = reverse("billableitem-list")
        response = self.client.post(url, billable_item_data, format="json")
        self.assertEqual(response.status_code, 201)

    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_create_billable_items_without_clinical_order(self, mock_create_erp_login):
        """Test creating billable items."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }
        patient = baker.make(
            Patient,
            customer_id="e9fe2c6a-d60d-4722-a3c3-760e9c37b8ec",
            **self.ids_metadata,
        )
        queue = baker.make(Queue)
        baker.make(
            Visit,
            patient=patient,
            current_queue=queue,
            status="ARRIVED",
            **self.ids_metadata,
        )
        service_request = ServiceRequest.objects.latest("created")
        invoice = service_request.invoice
        clinical_order = service_request.clinical_order
        billable_item_data = {
            "product_id": "a1a8a97f-1a6a-4c7d-a64f-007f3ef75072",
            "pricelist_product_id": "fdd90a71-3ebe-444c-9a52-9aa79300a07b",
            "invoice": invoice.id,
            "name": "panadol",
            "quantity": 2,
            "price": 2000,
            "original_price": 2000,
        }

        url = reverse("billableitem-list")
        response = self.client.post(url, billable_item_data, format="json")
        self.assertEqual(response.status_code, 201)
        billable_item = BillableItem.objects.latest("created")
        self.assertEqual(billable_item.clinical_order, clinical_order)

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch("sil_advantage.billing.views.get_erp_client")
    def test_recording_payments(self, mock_create_erp_login, mock_amount_due):
        """Test recording payments."""
        mock_erp = MagicMock()
        mock_erp.payment_receipts.create.return_value = {
            "id": "58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            "amount": "2500",
        }
        mock_erp.customer_invoice_payments.create.return_value = {
            "id": "7c1ba268-d574-4104-af8a-99339e2cee43",
        }
        mock_amount_due.return_value = Decimal("2500")
        mock_create_erp_login.return_value = mock_erp

        invoice = Invoice.objects.latest("created")
        invoice.sales_invoice_id = "46452480-0ec6-403d-953d-ff9cbf02c0e1"
        invoice.save()

        url = reverse("invoice-record-payment", kwargs={"pk": invoice.pk})
        self.client.post(
            url,
            {
                "amount": "2500",
                "payment_date": timezone.now()
                .replace(second=0, microsecond=0)
                .isoformat(),
                "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
                "payment_reference": "Q34DA34F",
                "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
            },
        )

        mock_erp.payment_receipts.create.assert_called_once_with(
            {
                "amount": Decimal("2500.0000"),
                "source_organisation_unit": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
                "organisation": str(invoice.organisation.id),
                "business_partner": UUID("1537169c-0716-4e0a-a71e-20d817c08a52"),
                "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
                "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
                "source": "CUSTOMER",
                "payment_date": timezone.now()
                .replace(second=0, microsecond=0)
                .isoformat(),
                "reference_number": "Q34DA34F",
                "source_document": UUID("46452480-0ec6-403d-953d-ff9cbf02c0e1"),
                "workflow_state": "DRAFT",
                "created_by": self.user.id,
                "updated_by": self.user.id,
            }
        )
        mock_erp.customer_invoice_payments.create.assert_called_once_with(
            {
                "amount": "2500.0000",
                "invoice": UUID("46452480-0ec6-403d-953d-ff9cbf02c0e1"),
                "payment": "58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
                "organisation": str(invoice.organisation.id),
                "created_by": self.user.id,
                "updated_by": self.user.id,
            }
        )

        self.visit.refresh_from_db()
        assert self.visit.status == "IN_PROGRESS"

        invoice.refresh_from_db()
        self.assertSequenceEqual(
            invoice.payments.values_list("payment_receipt_id", flat=True),
            [UUID("58ebc4b3-c088-4a76-9c4e-d112c801ae4c")],
        )

        # second payment
        mock_erp.payment_receipts.create.return_value = {
            "id": "822c1799-cf28-40df-9cb4-95e728362ec4",
            "amount": "2500",
        }
        mock_erp.customer_invoice_payments.create.return_value = {
            "id": "22e8fbca-b8e1-4ee5-89a5-3c5d4e47bae9",
        }
        self.client.post(
            url,
            {
                "amount": "2500",
                "payment_date": timezone.now()
                .replace(second=0, microsecond=0)
                .isoformat(),
                "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
                "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
            },
        )
        self.visit.refresh_from_db()
        assert self.visit.status == "IN_PROGRESS"

    @patch("sil_advantage.billing.views.get_erp_client")
    def test_process_payment_for_invoice_value_error(self, mock_create_erp_login):
        """Test ValueError is raised when sales_invoice_id is None."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp

        invoice = Invoice.objects.latest("created")
        invoice.save()

        request = MagicMock()
        request.user.guid = "test-user-guid"
        data = {
            "amount": "2500",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
            "payment_reference": "Q34DA34F",
            "payment_method_name": "Credit Card",
        }

        with self.assertRaises(ValueError) as context:
            utils.process_payment_for_invoice(request, invoice, data, mock_erp)

        self.assertEqual(
            str(context.exception),
            "The invoice does not have a sales invoice ID."
            " Payment cannot be processed without it.",
        )

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch("sil_advantage.billing.views.get_erp_client")
    def test_record_multiple_payments(self, mock_create_erp_login, mock_amount_due):
        """Test recording payments for multiple invoices."""
        mock_erp = MagicMock()
        mock_erp.payment_receipts.create.side_effect = [
            {"id": "58ebc4b3-c088-4a76-9c4e-d112c801ae4d", "amount": "1500"},
            {"id": "822c1799-cf28-40df-9cb4-95e728362ec5", "amount": "1810"},
        ]
        mock_erp.customer_invoice_payments.create.side_effect = [
            {"id": "7c1ba268-d574-4104-af8a-99339e2cee45"},
            {"id": "22e8fbca-b8e1-4ee5-89a5-3c5d4e47bae7"},
        ]
        mock_amount_due.return_value = Decimal("3310")
        mock_create_erp_login.return_value = mock_erp
        queue = baker.make(Queue, name="Consultation")
        self.visit.current_queue = queue
        self.visit.save()
        invoice = self.visit.service_requests.latest("created").invoice
        invoice.sales_invoice_id = "91847399-0e82-4b40-940c-0646be24d59f"
        invoice.invoice_number = "SIL/KIL/0782"
        invoice.save()
        baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_500,
            original_price=1_500,
            quantity=1,
        )
        queue2 = baker.make(Queue, name="Pharmacy")
        self.visit.current_queue = queue2
        self.visit.save()
        invoice2 = self.visit.service_requests.latest("created").invoice
        invoice2.sales_invoice_id = "4662eb8f-6c1c-4c5c-b0d1-0cc5fc2b33e1"
        invoice2.invoice_number = "SIL/KIL/0785"
        invoice2.save()
        baker.make(
            BillableItem,
            invoice=invoice2,
            name="Panadol 500mg",
            price=10,
            original_price=10,
            quantity=14,
        )
        baker.make(
            BillableItem,
            invoice=invoice2,
            name=" Ablation of endometriotic spots ",
            price=1_800,
            original_price=2_000,
            quantity=1,
        )
        invoice_ids = [
            invoice.pk,
            invoice2.pk,
        ]
        url = reverse("invoice-record-multiple-payments")
        response = self.client.post(
            url,
            {
                "invoice_ids": invoice_ids,
                "amount": "3300",
                "payment_date": "2023-01-11T21:00:00.000Z",
                "payment_method": "396e0182-377c-4266-b1b8-cfc44a272601",
                "payment_reference": "Q34DA34F",
                "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf88",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["detail"], "Payments recorded successfully.")
        response = self.client.post(
            url,
            {
                "invoice_ids": ["invalid_id"],
                "amount": "3300",
                "payment_date": "2023-01-11T21:00:00.000Z",
                "payment_method": "396e0182-377c-4266-b1b8-cfc44a272601",
                "payment_reference": "Q34DA34F",
                "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf88",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(
            url,
            {
                "invoice_ids": invoice_ids,
                "amount": "3300",
                "payment_date": "2023-01-11T21:00:00.000Z",
                "payment_method": "396e0182-377c-4266-b1b8-cfc44a272601",
                "payment_reference": "Q34DA34F",
                "currency": "2313",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @patch(MOCK_ROOT + "get_erp_client")
    def test_record_multiple_payments_invoices_not_found(self, mock_create_erp_login):
        """Test recording multiple invoices payments missing invoices."""
        url = reverse("invoice-record-multiple-payments")
        response = self.client.post(
            url,
            {
                "invoice_ids": [999],
                "amount": "3000",
                "payment_date": "2023-01-11T21:00:00.000Z",
                "payment_method": "396e0182-377c-4266-b1b8-cfc44a272601",
                "payment_reference": "Q34DA34F",
                "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf88",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(MOCK_ROOT + "get_erp_client")
    def test_refund_payments(self, mock_create_erp_login):
        """Test refunding of payments."""
        mock_erp = MagicMock()
        mock_erp.payment_receipts.transition.return_value = {
            "id": "58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            "workflow_state": "CLOSED",
        }
        mock_create_erp_login.return_value = mock_erp
        invoice = Invoice.objects.latest("created")
        baker.make(
            Payment,
            invoice=invoice,
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
            **self.ids_metadata,
        )

        url = reverse("invoice-refund-payment", kwargs={"pk": invoice.id})

        result = self.client.post(
            url,
            {
                "payment_receipt_id": "58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            },
        )
        assert result.json() == {
            "id": "58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            "workflow_state": "CLOSED",
        }

        invoice.refresh_from_db()
        mock_erp.payment_receipts.transition.assert_called_once_with(
            UUID("58ebc4b3-c088-4a76-9c4e-d112c801ae4c"),
            "DRAFT_CLOSED",
        )
        self.assertCountEqual(
            invoice.payments.values_list("payment_receipt_id", flat=True),
            [],
        )

    @patch(MOCK_ROOT + "get_erp_client")
    def test_refund_payments_bad_payment(self, mock_create_erp_login):
        """Test refunding a non-existent/bad payment."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp

        invoice = Invoice.objects.latest("created")

        url = reverse("invoice-refund-payment", kwargs={"pk": invoice.id})
        result = self.client.post(
            url,
            {
                "payment_receipt_id": "58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            },
        )
        assert result.json() == ["The payment is not part of this invoice."]

        mock_erp.payment_receipts.transition.assert_not_called()

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch(MOCK_TASKS_ROOT + "get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_recording_refunds(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Test creating refunds and refund lines."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_erp.payment_receipts.create.return_value = {
            "id": "117b7f08-8b97-49aa-920e-e846e79b5ea3",
            "amount": (-1 * Decimal("2500.0000")),
            "payment_date": "2023-01-11T21:00:00.000Z",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "payment_reference": "Q34DA34F",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
        }
        mock_amount_due.return_value = Decimal("4000")
        mock_tasks_erp_client.return_value = mock_erp

        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")

        context = {
            "organisation": invoice.organisation,
            "branch_id": invoice.branch_id,
            "workstation_id": invoice.workstation_id,
            "department_id": invoice.department_id,
            "created_by": invoice.updated_by,
            "updated_by": invoice.updated_by,
        }

        baker.make(
            Payment,
            invoice=invoice,
            payment_method="ba443d10-1e86-42e6-969b-6b35f0c5c8c3",
            currency="a6d4211c-61af-45f0-ac6d-358e1a1ad25d",
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
            amount=4_000,
        )

        url = reverse("invoice-refund", kwargs={"pk": invoice.pk})
        # Valid refund request
        response = self.client.post(
            url,
            {
                "reason": "Waived service sale.",
                "kra_reason_code": "11",
                "sales_credit_note_id": "9e221ca3-7aff-4365-a745-ea168e5d361e",
            },
            format="json",
        )
        assert response.status_code == 200, response.content
        refund = Refund.objects.get(invoice=invoice)
        assert refund.reason == "Waived service sale."
        assert refund.kra_reason_code == "11"

        refund_lines = utils.get_refundable_invoice_lines(
            invoice, context, refund, invoice.invoice_lines.all()
        )
        self.assertEqual(len(refund_lines), 0)

        mock_erp.sales_credit_notes.transition.assert_called_once_with(
            refund.sales_credit_note_id,
            "DRAFT_SUBMIT_APPROVE",
        )

        assert Payment.objects.count() == 2

        mock_erp.payment_receipts.transition.assert_called_once_with(
            UUID("117b7f08-8b97-49aa-920e-e846e79b5ea3"),
            "DRAFT_SUBMIT_APPROVE",
        )

    @patch("sil_advantage.billing.tasks.get_erp_client")
    @patch("sil_advantage.billing.models.Refund.objects.get")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    def test_process_refund_on_erp(
        self, mock_sync_updates, mock_refund_get, mock_get_erp_client
    ):
        """Test exceptions and refund not found during refund processing."""
        mock_erp = MagicMock()
        mock_get_erp_client.return_value = mock_erp

        refund_id = uuid.uuid4()
        mock_refund_get.side_effect = None
        refund = MagicMock()
        mock_refund_get.return_value = refund

        mock_sync_updates.side_effect = Exception("Processing error")

        with self.assertLogs("sil_advantage.billing.tasks", level="ERROR") as error:
            with self.assertRaisesRegex(Exception, "Processing error"):
                tasks.process_refund_on_erp(refund_id)

        if error.output:
            self.assertIn(f"Failed to process refund {refund_id}", error.output[0])
        else:
            self.fail("No log messages were captured during the task execution.")

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch(MOCK_TASKS_ROOT + "get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_creating_full_refund_from_partial_quantity_left_less_than_zero(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Test full refund when remaining partial refund quantity is less than zero."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_erp.payment_receipts.create.return_value = {
            "id": "117b7f08-8b97-49aa-920e-e846e79b5ea3",
            "amount": (-1 * Decimal("2500.0000")),
            "payment_date": "2023-01-11T21:00:00.000Z",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "payment_reference": "Q34DA34F",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
        }
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp
        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")

        context = {
            "organisation": invoice.organisation,
            "branch_id": invoice.branch_id,
            "workstation_id": invoice.workstation_id,
            "department_id": invoice.department_id,
            "created_by": invoice.updated_by,
            "updated_by": invoice.updated_by,
        }
        invoice_line = baker.make(
            BillableItem,
            invoice=invoice,
            name="Panadol Extra",
            price=800,
            original_price=800,
            quantity=5,
        )
        baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=2500,
            original_price=2500,
            quantity=1,
        )
        baker.make(
            BillableItem,
            invoice=invoice,
            name="Amoxil",
            price=800,
            original_price=800,
            quantity=5,
        )

        # Step 1: Create a partial refund
        url = reverse("invoice-refund-line", kwargs={"pk": invoice.pk})
        response = self.client.post(
            url,
            {
                "reason": "Partial refund for services.",
                "kra_reason_code": "01",
                "invoice_lines": [
                    {"id": invoice_line.id, "amount": 700, "quantity": 5}
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        partial_refund = Refund.objects.get(invoice=invoice)
        self.assertEqual(partial_refund.refund_lines.count(), 1)
        self.assertEqual(partial_refund.refund_amount, 3500)
        self.assertEqual(partial_refund.invoice.refund_status, PARTIALLY_REFUNDED)

        refundable_lines = utils.get_refundable_invoice_lines(
            invoice, context, partial_refund, invoice.invoice_lines.all()
        )
        self.assertEqual(len(refundable_lines), 3)
        assert refundable_lines[0].amount == 100
        assert refundable_lines[0].quantity == 5

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch(MOCK_TASKS_ROOT + "get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_creating_full_refund_from_partial_quantity_left_more_than_zero(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Test full refund when remaining partial refund quantity is more than zero."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_erp.payment_receipts.create.return_value = {
            "id": "117b7f08-8b97-49aa-920e-e846e79b5ea3",
            "amount": (-1 * Decimal("2500.0000")),
            "payment_date": "2023-01-11T21:00:00.000Z",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "payment_reference": "Q34DA34F",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
        }
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp
        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")

        context = {
            "organisation": invoice.organisation,
            "branch_id": invoice.branch_id,
            "workstation_id": invoice.workstation_id,
            "department_id": invoice.department_id,
            "created_by": invoice.updated_by,
            "updated_by": invoice.updated_by,
        }
        invoice_line1, invoice_line2, invoice_line3 = baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=iter([600, 700, 800]),
            original_price=iter([600, 700, 800]),
            quantity=5,
            _quantity=3,
        )

        # Step 1: Create a partial refund
        url = reverse("invoice-refund-line", kwargs={"pk": invoice.pk})
        response = self.client.post(
            url,
            {
                "reason": "Partial refund for services.",
                "kra_reason_code": "01",
                "invoice_lines": [
                    {"id": invoice_line2.id, "amount": 700, "quantity": 2}
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        partial_refund = Refund.objects.get(invoice=invoice)
        self.assertEqual(partial_refund.refund_lines.count(), 1)
        self.assertEqual(partial_refund.refund_amount, 1400)
        self.assertEqual(partial_refund.invoice.refund_status, PARTIALLY_REFUNDED)

        refundable_lines = utils.get_refundable_invoice_lines(
            invoice, context, partial_refund, invoice.invoice_lines.all()
        )
        self.assertEqual(len(refundable_lines), 3)
        remaining_quantity_line1 = next(
            line for line in refundable_lines if line.invoice_line == invoice_line1
        )
        self.assertEqual(remaining_quantity_line1.quantity, 5)

        # invoice_line2 and invoice_line3 should be fully refundable
        remaining_quantity_line2 = next(
            line for line in refundable_lines if line.invoice_line == invoice_line2
        )
        remaining_quantity_line3 = next(
            line for line in refundable_lines if line.invoice_line == invoice_line3
        )
        self.assertEqual(remaining_quantity_line2.quantity, 3)
        self.assertEqual(remaining_quantity_line3.quantity, invoice_line3.quantity)

        # Clear mock call history after partial refund
        mock_erp.sales_credit_notes.transition.reset_mock()

        # Step 2: Create a full refund from the partial refund
        url = reverse("invoice-refund", kwargs={"pk": invoice.pk})
        response = self.client.post(
            url,
            {
                "reason": "Full refund after partial.",
                "kra_reason_code": "11",
                "sales_credit_note_id": "9e221ca3-7aff-4365-a745-ea168e5d361e",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        full_refund = Refund.objects.get(id=response.data["id"])
        self.assertEqual(full_refund.reason, "Full refund after partial.")
        self.assertEqual(full_refund.kra_reason_code, "11")
        self.assertEqual(full_refund.refund_lines.count(), 3)

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch(MOCK_TASKS_ROOT + "get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_creating_full_refund_when_no_lines_refunded_yet(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Test creating a full refund when no lines have been refunded yet."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_erp.payment_receipts.create.return_value = {
            "id": "117b7f08-8b97-49aa-920e-e846e79b5ea3",
            "amount": (-1 * Decimal("2500.0000")),
            "payment_date": "2023-01-11T21:00:00.000Z",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "payment_reference": "Q34DA34F",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
        }
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp
        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")

        context = {
            "organisation": invoice.organisation,
            "branch_id": invoice.branch_id,
            "workstation_id": invoice.workstation_id,
            "department_id": invoice.department_id,
            "created_by": invoice.updated_by,
            "updated_by": invoice.updated_by,
        }
        invoice_line1, invoice_line2, invoice_line3 = baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=iter([600, 700, 800]),
            original_price=iter([600, 700, 800]),
            quantity=5,
            _quantity=3,
        )
        invoice.invoice_lines.all = MagicMock(
            return_value=[invoice_line1, invoice_line2, invoice_line3]
        )
        # Step 1: Verify no refunds exist
        refundable_lines = utils.get_refundable_invoice_lines(
            invoice, context, None, invoice.invoice_lines.all()
        )
        self.assertEqual(len(refundable_lines), 3)

        # Ensure that all invoice lines have corresponding refund lines
        for line in refundable_lines:
            self.assertEqual(line.quantity, line.invoice_line.quantity)
            self.assertEqual(line.amount, line.invoice_line.price)
            self.assertEqual(line.invoice_line.invoice, invoice)

        # Check that the refund lines are created when no lines have been refunded
        for line in invoice.invoice_lines.all():
            corresponding_refund_line = line.refund_line.first()
            self.assertIsNone(corresponding_refund_line)

            refund_line = RefundLine(
                refund=None,
                invoice_line=line,
                quantity=line.quantity,
                amount=line.price,
                **context,
            )
            self.assertNotIn(refund_line, refundable_lines)

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch(MOCK_TASKS_ROOT + "get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_invoice_lines_filtering(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Test filtering invoice lines based on payload."""
        mock_erp = MagicMock()
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_erp.payment_receipts.create.return_value = {
            "id": "117b7f08-8b97-49aa-920e-e846e79b5ea3",
            "amount": (-1 * Decimal("2500.0000")),
            "payment_date": "2023-01-11T21:00:00.000Z",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "payment_reference": "Q34DA34F",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
        }
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp

        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")
        invoice_line_1 = baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_000,
            original_price=1_000,
            quantity=2,
        )

        baker.make(
            Payment,
            invoice=invoice,
            payment_method="ba443d10-1e86-42e6-969b-6b35f0c5c8c3",
            currency="a6d4211c-61af-45f0-ac6d-358e1a1ad25d",
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
            amount=4_000,
        )

        payload = {
            "reason": "Waived service sale.",
            "kra_reason_code": "11",
            "sales_credit_note_id": "9e221ca3-7aff-4365-a745-ea168e5d361e",
            "invoice_lines": [str(invoice_line_1.id)],
        }

        url = reverse("invoice-refund", kwargs={"pk": invoice.pk})
        response = self.client.post(url, payload, format="json")

        assert response.status_code == 200, response.content
        refund = Refund.objects.get(invoice=invoice)
        assert refund.reason == "Waived service sale."
        assert refund.kra_reason_code == "11"

        mock_erp.sales_credit_notes.transition.assert_called_once_with(
            refund.sales_credit_note_id,
            "DRAFT_SUBMIT_APPROVE",
        )

        assert Payment.objects.count() == 2

        mock_erp.payment_receipts.transition.assert_called_once_with(
            UUID("117b7f08-8b97-49aa-920e-e846e79b5ea3"),
            "DRAFT_SUBMIT_APPROVE",
        )

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_recording_refunds_on_invoice_6_months_older(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Test creating refunds for invoice that is 6 months old."""
        mock_erp = MagicMock()
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_erp.payment_receipts.create.return_value = {
            "id": "117b7f08-8b97-49aa-920e-e846e79b5ea3",
            "amount": (-1 * Decimal("2500.0000")),
            "payment_date": "2023-01-11T21:00:00.000Z",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "payment_reference": "Q34DA34F",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
        }
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp

        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
            created=timezone.now() - timedelta(days=180),
        )
        invoice = Invoice.objects.latest("created")

        baker.make(
            Payment,
            invoice=invoice,
            payment_method="ba443d10-1e86-42e6-969b-6b35f0c5c8c3",
            currency="a6d4211c-61af-45f0-ac6d-358e1a1ad25d",
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
            amount=4_000,
        )

        url = reverse("invoice-refund", kwargs={"pk": invoice.pk})
        response = self.client.post(
            url,
            data={
                "reason": "Test refund.",
                "kra_reason_code": "11",
                "sales_credit_note_id": "9e221ca3-7aff-4365-a745-ea168e5d361e",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot refund invoices older than 6 months.", str(response.data))

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch(MOCK_TASKS_ROOT + "get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_recording_invoice_line_refunds_on_invoice_6_months_older(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Test creating refunds for invoice that is 6 months old."""
        mock_erp = MagicMock()
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_erp.payment_receipts.create.return_value = {
            "id": "117b7f08-8b97-49aa-920e-e846e79b5ea3",
            "amount": (-1 * Decimal("2500.0000")),
            "payment_date": "2023-01-11T21:00:00.000Z",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "payment_reference": "Q34DA34F",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
        }
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp

        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
            created=timezone.now() - timedelta(days=180),
        )
        invoice = Invoice.objects.latest("created")

        invoice_line = baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_000,
            original_price=1_000,
            quantity=4,
        )

        baker.make(
            Payment,
            invoice=invoice,
            payment_method="ba443d10-1e86-42e6-969b-6b35f0c5c8c3",
            currency="a6d4211c-61af-45f0-ac6d-358e1a1ad25d",
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
            amount=4_000,
        )

        url = reverse("invoice-refund-line", kwargs={"pk": invoice.pk})
        response = self.client.post(
            url,
            data={
                "reason": "Test refund.",
                "kra_reason_code": "11",
                "invoice_lines": [
                    {"id": invoice_line.id, "amount": 200, "quantity": 3}
                ],
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot refund invoices older than 6 months.", str(response.data))

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch(MOCK_TASKS_ROOT + "get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_recording_refunds_with_invalid_billableitem(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Test creating refunds with a non-existent BillableItem."""
        mock_erp = MagicMock()
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_erp.payment_receipts.create.return_value = {
            "id": "117b7f08-8b97-49aa-920e-e846e79b5ea3",
            "amount": (-1 * Decimal("2500.0000")),
            "payment_date": "2023-01-11T21:00:00.000Z",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "payment_reference": "Q34DA34F",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
        }
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp

        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")
        baker.make(
            Payment,
            invoice=invoice,
            payment_method="ba443d10-1e86-42e6-969b-6b35f0c5c8c3",
            currency="a6d4211c-61af-45f0-ac6d-358e1a1ad25d",
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
            amount=4_000,
        )

        url = reverse("invoice-refund-line", kwargs={"pk": invoice.pk})

        response = self.client.post(
            url,
            {
                "reason": "Invalid item.",
                "kra_reason_code": "11",
                "sales_credit_note_id": "9e221ca3-7aff-4365-a745-ea168e5d361e",
                "invoice_lines": [
                    {"id": 9999, "amount": 200, "quantity": 4},
                ],
            },
            format="json",
        )
        assert response.status_code == 400
        assert "BillableItem with this id does not exist." in str(response.data)

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_recording_refunds_with_negative_quantity(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Test creating refunds with a negative quantity."""
        mock_erp = MagicMock()
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_erp.payment_receipts.create.return_value = {
            "id": "117b7f08-8b97-49aa-920e-e846e79b5ea3",
            "amount": (-1 * Decimal("2500.0000")),
            "payment_date": "2023-01-11T21:00:00.000Z",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "payment_reference": "Q34DA34F",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
        }
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp

        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")
        invoice_line = baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_000,
            original_price=1_000,
            quantity=4,
        )

        baker.make(
            Payment,
            invoice=invoice,
            payment_method="ba443d10-1e86-42e6-969b-6b35f0c5c8c3",
            currency="a6d4211c-61af-45f0-ac6d-358e1a1ad25d",
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
            amount=4_000,
        )

        url = reverse("invoice-refund-line", kwargs={"pk": invoice.pk})

        response = self.client.post(
            url,
            {
                "reason": "Wrong Quantity.",
                "kra_reason_code": "11",
                "sales_credit_note_id": "9e221ca3-7aff-4365-a745-ea168e5d361e",
                "invoice_lines": [
                    {"id": invoice_line.id, "amount": 200, "quantity": -1},
                ],
            },
            format="json",
        )
        assert response.status_code == 400
        assert "Quantity cannot be negative." in str(response.data)

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_recording_refunds_with_excess_quantity(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Test creating refunds with a greater quantity than BillableItem quantity."""
        mock_erp = MagicMock()
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_erp.payment_receipts.create.return_value = {
            "id": "117b7f08-8b97-49aa-920e-e846e79b5ea3",
            "amount": (-1 * Decimal("2500.0000")),
            "payment_date": "2023-01-11T21:00:00.000Z",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "payment_reference": "Q34DA34F",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
        }
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp

        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")
        invoice_line = baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_000,
            original_price=1_000,
            quantity=4,
        )

        baker.make(
            Payment,
            invoice=invoice,
            payment_method="ba443d10-1e86-42e6-969b-6b35f0c5c8c3",
            currency="a6d4211c-61af-45f0-ac6d-358e1a1ad25d",
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
            amount=4_000,
        )

        url = reverse("invoice-refund-line", kwargs={"pk": invoice.pk})

        response = self.client.post(
            url,
            {
                "reason": "Wrong Quantity.",
                "kra_reason_code": "11",
                "sales_credit_note_id": "9e221ca3-7aff-4365-a745-ea168e5d361e",
                "invoice_lines": [
                    {"id": invoice_line.id, "amount": 200, "quantity": 10},
                ],
            },
            format="json",
        )
        assert response.status_code == 400
        assert {
            "detail": [
                ErrorDetail(
                    string="Quantity cannot exceed the available quantity.",
                    code="invalid",
                )
            ]
        }

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_recording_refunds_with_excess_unit_amount(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Test creating refunds with a greater unit price than BillableItem price."""
        mock_erp = MagicMock()
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_erp.payment_receipts.create.return_value = {
            "id": "117b7f08-8b97-49aa-920e-e846e79b5ea3",
            "amount": (-1 * Decimal("2500.0000")),
            "payment_date": "2023-01-11T21:00:00.000Z",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "payment_reference": "Q34DA34F",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
        }
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp

        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")
        invoice_line = baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_000,
            original_price=1_000,
            quantity=4,
        )

        baker.make(
            Payment,
            invoice=invoice,
            payment_method="ba443d10-1e86-42e6-969b-6b35f0c5c8c3",
            currency="a6d4211c-61af-45f0-ac6d-358e1a1ad25d",
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
            amount=4_000,
        )

        url = reverse("invoice-refund-line", kwargs={"pk": invoice.pk})

        response = self.client.post(
            url,
            {
                "reason": "Wrong Quantity.",
                "kra_reason_code": "11",
                "sales_credit_note_id": "9e221ca3-7aff-4365-a745-ea168e5d361e",
                "invoice_lines": [
                    {"id": invoice_line.id, "amount": 1200, "quantity": 3},
                ],
            },
            format="json",
        )
        assert response.status_code == 400
        assert "Amount cannot exceed the original BillableItem price." in str(
            response.data
        )

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch(MOCK_TASKS_ROOT + "get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_refunding_a_subset_of_invoice_lines(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Test creating refunds and refund lines."""
        mock_erp = MagicMock()
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp

        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")

        _, invoice_line2, invoice_line3 = baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=iter([600, 700, 800]),
            original_price=iter([600, 700, 800]),
            quantity=5,
            _quantity=3,
        )

        url = reverse("invoice-refund-line", kwargs={"pk": invoice.pk})
        response = self.client.post(
            url,
            {
                "reason": "Waived service sale.",
                "kra_reason_code": "11",
                "invoice_lines": [
                    {"id": invoice_line2.id, "amount": 100, "quantity": 4},
                    {"id": invoice_line3.id, "amount": 200, "quantity": 3},
                ],
            },
        )
        assert response.status_code == 200, response.content
        refund = Refund.objects.get(invoice=invoice)
        assert refund.refund_lines.count() == 2
        assert refund.amount == 7500

        erp = mock_tasks_erp_client.return_value
        erp.sales_credit_notes.transition.assert_called_once_with(
            refund.sales_credit_note_id,
            "DRAFT_SUBMIT_APPROVE",
        )

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch(MOCK_ROOT + "get_erp_client")
    def test_refund_invalid_invoice_workflow_state(
        self, mock_create_erp_login, mock_amount_due
    ):
        """Verify that refund is not issued on non-processed invoice."""
        mock_erp = MagicMock()
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp

        invoice = Invoice.objects.latest("created")

        url = reverse("invoice-refund", kwargs={"pk": invoice.pk})
        response = self.client.post(
            url,
            {"reason": "Waived service sale.", "kra_reason_code": "11"},
        )
        assert response.status_code == 400
        assert response.data == {"detail": ["Kindly ensure the invoice is processed."]}

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch(MOCK_TASKS_ROOT + "get_erp_client")
    @patch(MOCK_TASKS_ROOT + "sync_updates_to_remote")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_refund_fully_refunded_status(
        self,
        mock_create_erp_login,
        mock_sync_to_erp,
        mock_tasks_erp_client,
        mock_amount_due,
    ):
        """Verify that refund cannot be issued on fully refunded invoice."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_erp.payment_receipts.create.return_value = {
            "id": "117b7f08-8b97-49aa-920e-e846e79b5ea3",
            "amount": (-1 * Decimal("2500.0000")),
            "payment_date": "2023-01-11T21:00:00.000Z",
            "payment_method": "396e0182-377c-4266-b1b8-cfc44a272602",
            "payment_reference": "Q34DA34F",
            "currency": "9c8cd6ff-fb35-4d83-8e96-685139d0cf89",
        }
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp
        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")

        context = {
            "organisation": invoice.organisation,
            "branch_id": invoice.branch_id,
            "workstation_id": invoice.workstation_id,
            "department_id": invoice.department_id,
            "created_by": invoice.updated_by,
            "updated_by": invoice.updated_by,
        }
        invoice_line = baker.make(
            BillableItem,
            invoice=invoice,
            name="Panadol Extra",
            price=800,
            original_price=800,
            quantity=5,
        )
        # Step 1: Create a partial refund
        url = reverse("invoice-refund-line", kwargs={"pk": invoice.pk})
        response = self.client.post(
            url,
            {
                "reason": "Partial refund for services.",
                "kra_reason_code": "01",
                "invoice_lines": [
                    {"id": invoice_line.id, "amount": 800, "quantity": 5}
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        partial_refund = Refund.objects.get(invoice=invoice)
        partial_refund.workflow_state = "SUBMITTED"
        partial_refund.save()
        self.assertEqual(partial_refund.refund_lines.count(), 1)
        self.assertEqual(partial_refund.refund_amount, 4000)
        self.assertEqual(partial_refund.invoice.refund_status, FULLY_REFUNDED)

        # Step 2: Attempt to create another refund on the fully refunded invoice
        with self.assertRaises(ValidationError) as context:
            baker.make(Refund, invoice=invoice)
        self.assertIn(
            "This invoice has already been fully refunded.", str(context.exception)
        )

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch(MOCK_ROOT + "get_erp_client")
    def test_invoice_line_refund_with_invalid_invoice_workflow_state(
        self, mock_create_erp_login, mock_amount_due
    ):
        """Verify that refund is not issued on non-processed invoice."""
        mock_erp = MagicMock()
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_amount_due.return_value = Decimal("4000")
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }
        mock_create_erp_login.return_value = mock_erp

        invoice = Invoice.objects.latest("created")

        invoice_line = baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_000,
            original_price=1_000,
            quantity=4,
        )

        url = reverse("invoice-refund-line", kwargs={"pk": invoice.pk})
        response = self.client.post(
            url,
            {
                "reason": "Waived service sale.",
                "kra_reason_code": "11",
                "invoice_lines": [
                    {"id": invoice_line.id, "amount": 200, "quantity": 3}
                ],
            },
        )
        assert response.status_code == 400
        assert response.data == {"detail": ["Kindly ensure the invoice is processed."]}

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    @patch(MOCK_ROOT + "get_erp_client")
    def test_refunds_already_exists(
        self, mock_create_erp_login, mock_tasks_erp_client, mock_amount_due
    ):
        """Verify a processed invoice can't have more than one refund."""
        mock_erp = MagicMock()
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_amount_due.return_value = Decimal("4000")
        mock_create_erp_login.return_value = mock_erp
        mock_tasks_erp_client.return_value = mock_erp

        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")

        baker.make(
            Refund,
            invoice=invoice,
            reason="Waived service sale.",
            kra_reason_code="11",
            organisation=invoice.organisation,
            **self.ids_metadata,
        )

        url = reverse("invoice-refund", kwargs={"pk": invoice.pk})
        response = self.client.post(
            url,
            {"reason": "Waived service sale.", "kra_reason_code": "11"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch.object(Invoice, "amount_due", new_callable=PropertyMock)
    @patch(MOCK_ROOT + "get_erp_client")
    def test_invoice_line_refunds_already_exists(
        self, mock_create_erp_login, mock_amount_due
    ):
        """Verify a processed invoice can't have more than one refund."""
        mock_erp = MagicMock()
        mock_erp.sales_credit_notes.transition.return_value = ""
        mock_amount_due.return_value = Decimal("4000")
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }
        mock_create_erp_login.return_value = mock_erp

        Invoice.objects.update(
            workflow_state="PROCESSED",
            sales_invoice_id="46452480-0ec6-403d-953d-ff9cbf02c0e1",
        )
        invoice = Invoice.objects.latest("created")

        invoice_line = baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_000,
            original_price=1_000,
            quantity=4,
        )

        baker.make(
            Refund,
            invoice=invoice,
            reason="Waived service sale.",
            kra_reason_code="11",
            organisation=invoice.organisation,
            **self.ids_metadata,
        )

        url = reverse("invoice-refund-line", kwargs={"pk": invoice.pk})
        response = self.client.post(
            url,
            {
                "reason": "Waived service sale.",
                "kra_reason_code": "11",
                "invoice_lines": [
                    {"id": invoice_line.id, "amount": 200, "quantity": 3}
                ],
            },
        )
        assert response.data == [
            ErrorDetail(
                string=("This invoice line has an applied refund to it."),
                code="invalid",
            )
        ]


class WalletsViewTestCase(LoggedInMixin):
    """Test Wallets View."""

    url = reverse("wallets")

    @patch(MOCK_ROOT + "utils.get_wallet_balances")
    def test_listing_wallets(self, mock_balances):
        """Test listing wallets."""
        mock_balances.return_value = {
            "bulk_sms_account": {
                "type": "bulk_sms_account",
                "balance": "2500",
            }
        }
        response = self.client.get(self.url)
        assert response.status_code == 200

    @patch(MOCK_ROOT + "utils.get_wallet_balances")
    def test_no_wallets(self, mock_balances):
        """Test no wallets."""
        mock_balances.return_value = None
        response = self.client.get(self.url)
        assert response.status_code == 204
