"""Test billing models."""
import re
from copy import deepcopy
from decimal import Decimal
from itertools import cycle
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import UUID, uuid4

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from model_bakery import baker
from sil_wrapper_utils.exceptions import ItemNotFound

from sil_advantage.billing import FULLY_REFUNDED, NOT_REFUNDED
from sil_advantage.billing.models import (
    BillableItem,
    ClinicalOrder,
    Invoice,
    Payment,
    Refund,
    RefundLine,
    check_stock_quantity,
)
from sil_advantage.integrations.tasks import sync_updates_to_remote
from sil_advantage.patients.models import Patient
from sil_advantage.visits.models import Queue, ServiceRequest, Visit
from tests.common.test_common_views import LoggedInMixin


@override_settings(
    ERP_API_CONFIG={
        "api_host": "erp.slade360.co.ke/api",
        "api_scheme": "https",
        "oauth_client_id": "i-am-client-ID",
        "oauth_client_secret": "neno-siri",
        "user_email": "advantage_test@slade360.co.ke",
        "user_password": "Some=SecurePassword!",
        "token_url": "https://authserver.advantage.slade360.co.ke/",
    }
)
class ClinicalOrderModelTestCase(LoggedInMixin):
    """Test Clinical Order Model."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        user_id_metadata = {
            "created_by": self.user.id,
            "updated_by": self.user.id,
        }
        patient = baker.make(
            Patient,
            customer_id="1537169c-0716-4e0a-a71e-20d817c08a52",
            **user_id_metadata,
        )
        queue = baker.make(Queue)
        self.visit = baker.make(
            Visit,
            patient=patient,
            current_queue=queue,
            status="ARRIVED",
            **user_id_metadata,
        )
        self.service_request = ServiceRequest.objects.latest("created")
        self.service_request.status = "IN_PROGRESS"
        self.service_request.save()

    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_erp_sales_orders_payload(self, mock_create_erp_login):
        """Test creating the sales order payload."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp

        order = ClinicalOrder.objects.latest("created")
        assert order.erp_sales_orders_payload == {
            "customer": "1537169c-0716-4e0a-a71e-20d817c08a52",
            "source_organisation_unit": "None",
            "organisation": str(order.organisation.id),
            "workflow_state": "DRAFT",
        }


@override_settings(
    ERP_API_CONFIG={
        "api_host": "erp.slade360.co.ke/api",
        "api_scheme": "https",
        "oauth_client_id": "i-am-client-ID",
        "oauth_client_secret": "neno-siri",
        "user_email": "advantage_test@slade360.co.ke",
        "user_password": "Some=SecurePassword!",
        "token_url": "https://authserver.advantage.slade360.co.ke/",
    },
)
class InvoiceModelTestCase(LoggedInMixin):
    """Test Invoice Model."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.user_id_metadata = {
            "created_by": self.user.id,
            "updated_by": self.user.id,
            "department_id": "6db73406-4d24-445b-9896-564eb1a480b4",
        }
        self.patient = baker.make(
            Patient,
            customer_id="1537169c-0716-4e0a-a71e-20d817c08a52",
            **self.user_id_metadata,
        )
        self.queue = baker.make(Queue)

    @override_settings(SYNC_WITH_ERP=True)
    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_sync_creation_with_erp(self, mock_create_erp_login):
        """Test syncing invoice creation with the ERP."""
        mock_erp = MagicMock()
        mock_erp.sales_invoices.create.return_value = {
            "id": "5a41d7bb-fcc9-4cf8-ac65-4dfd1a882ad8",
            "document_number": "INV78",
            "workflow_state": "SUBMITTED",
        }
        mock_create_erp_login.return_value = mock_erp

        visit = baker.make(
            Visit,
            patient=self.patient,
            current_queue=self.queue,
            status="ARRIVED",
            **self.user_id_metadata,
        )
        invoice = Invoice.objects.latest("created")
        mock_erp.sales_invoices.create.assert_called_once_with(
            {
                "invoice_date": visit.start,
                "customer": "1537169c-0716-4e0a-a71e-20d817c08a52",
                "secondary_customer": "1537169c-0716-4e0a-a71e-20d817c08a52",
                "sales_type": str(visit.billing_class).lower(),
                "source_organisation_unit": "6db73406-4d24-445b-9896-564eb1a480b4",
                "organisation": str(invoice.organisation.id),
                "workflow_state": "DRAFT",
                "currency": None,
                "payment_method": None,
                "created_by": "1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
                "updated_by": "1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
            }
        )
        invoice.refresh_from_db()
        assert str(invoice.sales_invoice_id) == "5a41d7bb-fcc9-4cf8-ac65-4dfd1a882ad8"
        assert invoice.invoice_number == "INV78"
        assert invoice.workflow_state == "SUBMITTED"
        invoice._old_transition_value = "SUBMITTED"

    @override_settings(SYNC_WITH_ERP=True)
    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_sync_updates_with_erp(self, mock_create_erp_login):
        """Test syncing invoice updates with the ERP."""
        mock_erp = MagicMock()
        mock_erp.sales_invoices.create.return_value = {
            "id": "5a41d7bb-fcc9-4cf8-ac65-4dfd1a882ad8",
            "document_number": "INV78",
            "workflow_state": "SUBMITTED",
        }
        mock_erp.sales_invoices.update.return_value = {
            "id": "5a41d7bb-fcc9-4cf8-ac65-4dfd1a882ad8",
            "document_number": "INV78",
            "workflow_state": "PROCESSED",
        }
        mock_create_erp_login.return_value = mock_erp

        visit = baker.make(
            Visit,
            patient=self.patient,
            current_queue=self.queue,
            status="ARRIVED",
            **self.user_id_metadata,
        )
        invoice = Invoice.objects.latest("created")
        baker.make(
            Payment,
            invoice=invoice,
            currency="f6e049a0-10fd-4d9f-8470-571c9efa546c",
            payment_method_name="4f026ad4-2b8e-4761-a0cc-4d174bb0dad8",
        )
        invoice.workflow_state = "PROCESSED"
        invoice.save()
        first_payment = invoice.payments.first()
        mock_erp.sales_invoices.update.assert_called_once_with(
            UUID("5a41d7bb-fcc9-4cf8-ac65-4dfd1a882ad8"),
            {
                "invoice_date": visit.start,
                "customer": "1537169c-0716-4e0a-a71e-20d817c08a52",
                "secondary_customer": "1537169c-0716-4e0a-a71e-20d817c08a52",
                "sales_type": str(visit.billing_class).lower(),
                "source_organisation_unit": "6db73406-4d24-445b-9896-564eb1a480b4",
                "organisation": str(invoice.organisation.id),
                "workflow_state": "PROCESSED",
                "currency": first_payment.currency if first_payment else None,
                "payment_method": first_payment.payment_method
                if first_payment
                else None,
                "created_by": "1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
                "updated_by": "1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
            },
        )

    @override_settings(SYNC_WITH_ERP=True)
    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_sync_deletion_with_erp(self, mock_create_erp_login):
        """Test syncing invoice deletion with the ERP."""
        mock_erp = MagicMock()
        mock_erp.sales_invoices.create.return_value = {
            "id": "5a41d7bb-fcc9-4cf8-ac65-4dfd1a882ad8",
            "document_number": "INV78",
            "workflow_state": "SUBMITTED",
        }
        mock_erp.sales_invoices.delete.side_effect = ItemNotFound("She Gone.")
        mock_create_erp_login.return_value = mock_erp

        baker.make(
            Visit,
            patient=self.patient,
            current_queue=self.queue,
            status="ARRIVED",
            **self.user_id_metadata,
        )
        invoice = Invoice.objects.latest("created")

        deepcopy(invoice).delete()
        mock_erp.sales_invoices.delete.assert_called_once_with(
            UUID("5a41d7bb-fcc9-4cf8-ac65-4dfd1a882ad8")
        )
        assert Invoice.objects.filter(id=invoice.id).exists() is False

        # Attempt deletion with sync disabled
        mock_erp.reset_mock(side_effect=True, return_value=True)
        invoice._disable_sync = True
        invoice.delete()
        mock_erp.sales_invoice.delete.assert_not_called()

    @override_settings(SYNC_WITH_ERP=True)
    @patch.object(Invoice, "erp_sales_invoices_payload", new_callable=PropertyMock)
    @patch("sil_advantage.integrations.mixins.LOGGER")
    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_erp_creation_and_update_with_empty_payload(
        self, mock_create_erp_login, mock_logger, mock_invoice
    ):
        """Test ERP creation and updates with empty payloads."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_invoice.return_value = None

        baker.make(
            Visit,
            patient=self.patient,
            current_queue=self.queue,
            status="ARRIVED",
            **self.user_id_metadata,
        )
        invoice = Invoice.objects.latest("created")

        mock_logger.warning.assert_called_once_with(
            "Payload erp_sales_invoices_payload of object with ID "
            f"{invoice.pk} of type billing.invoice "
            "returned None (operation: CREATE)"
        )
        mock_erp.sales_invoices.create.assert_not_called()

    @patch("sil_advantage.integrations.mixins.LOGGER")
    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_unsupported_erp_operation(self, mock_create_erp_login, mock_logger):
        """Test operation not supported on the ERP workflow."""
        mock_create_erp_login.return_value = MagicMock()

        baker.make(
            Visit,
            patient=self.patient,
            current_queue=self.queue,
            status="ARRIVED",
            **self.user_id_metadata,
        )
        invoice = Invoice.objects.latest("created")
        invoice._perform_operation_on_erp("GET")
        mock_logger.warning.assert_called_once_with("Unsupported operation GET")

    @patch("sil_advantage.integrations.tasks.LOGGER")
    def test_operating_on_a_non_existent_object(self, mock_logger):
        """Test attempt to update a non-existent object."""
        pk = uuid4()
        sync_updates_to_remote("billing.invoice", pk, "ERP", "UPDATE")
        mock_logger.error.assert_called_once_with(
            f"Object with ID {pk} of type billing.invoice does not exist."
        )


class BillableItemModelTestCase(LoggedInMixin):
    """Test billable item model."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        user_id_metadata = {
            "created_by": self.user.id,
            "updated_by": self.user.id,
        }
        patient = baker.make(
            Patient,
            customer_id="1537169c-0716-4e0a-a71e-20d817c08a52",
            **user_id_metadata,
        )
        queue = baker.make(Queue)
        self.visit = baker.make(
            Visit,
            patient=patient,
            current_queue=queue,
            status="ARRIVED",
            **user_id_metadata,
        )
        self.service_request = ServiceRequest.objects.latest("created")

        order = ClinicalOrder.objects.latest("created")

        invoice = self.service_request.invoice
        invoice.sales_invoice_id = "8522f546-4c70-465f-a9fe-ea23c0032a6b"
        invoice.save()

        self.billable_item_1, self.billable_item_2 = baker.make(
            BillableItem,
            name="Panadol",
            product_id="a1a8a97f-1a6a-4c7d-a64f-007f3ef75072",
            pricelist_product_id="fdd90a71-3ebe-444c-9a52-9aa79300a07b",
            clinical_order=cycle([order, None]),
            invoice=cycle([None, invoice]),
            quantity=2,
            price=2_000,
            _quantity=2,
        )
        baker.make(Payment, invoice=invoice, amount=1_500)
        assert invoice.amount_due == 4_000
        assert invoice.amount_paid == 1_500

    def test_validate_order_or_invoice_provided(self):
        """Validate that an order or an invoice has been provided."""
        expected_error = re.escape(
            "A billable item must be linked to a clinical order and/or an invoice."
        )
        with pytest.raises(ValidationError, match=expected_error):
            baker.make(
                BillableItem,
                invoice=None,
                clinical_order=None,
            )

    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_validate_quantity_not_more_than_available_quantity(
        self, mock_create_erp_login
    ):
        """Test quantity is not more than available stock quantity."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": True,
            "quantity": 5,
        }

        invoice = self.service_request.invoice

        # Expected error message
        expected_error = re.escape(
            "Not enough stock for the product Panadol. " "Available: 5, required: 10."
        )

        # Test for ValidationError
        with pytest.raises(ValidationError, match=expected_error):
            baker.make(
                BillableItem,
                name="Panadol",
                product_id="a1a8a97f-1a6a-4c7d-a64f-007f3ef75072",
                pricelist_product_id="fdd90a71-3ebe-444c-9a52-9aa79300a07b",
                invoice=invoice,
                quantity=10,
                price=2_000,
                department_id="a1a8a97f-1a6a-4c7d-a64f-007f3ef75074",
            )

    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_validate_quantity_not_more_than_available_quantity_success(
        self, mock_create_erp_login
    ):
        """Test quantity is not more than available stock quantity."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": True,
            "quantity": 5,
        }

        invoice = self.service_request.invoice
        item = baker.make(
            BillableItem,
            product_id="a1a8a97f-1a6a-4c7d-a64f-007f3ef75072",
            pricelist_product_id="fdd90a71-3ebe-444c-9a52-9aa79300a07b",
            invoice=invoice,
            quantity=3,
            price=2_000,
            department_id="a1a8a97f-1a6a-4c7d-a64f-007f3ef75074",
        )
        assert item.id is not None

    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_check_stock_quantity_exception_handling(self, mock_get_erp_client):
        """Test check stock quantity exception handling."""
        mock_erp = MagicMock()
        mock_get_erp_client.return_value = mock_erp
        mock_erp.stockquantity.check_stock_quantity.side_effect = Exception("API Error")

        invoice = self.service_request.invoice
        item = baker.make(
            BillableItem,
            product_id="a1a8a97f-1a6a-4c7d-a64f-007f3ef75072",
            pricelist_product_id="fdd90a71-3ebe-444c-9a52-9aa79300a07b",
            invoice=invoice,
            quantity=3,
            price=2_000,
            department_id="a1a8a97f-1a6a-4c7d-a64f-007f3ef75074",
        )

        result = check_stock_quantity(item)
        assert result == {
            "stock_quantity_exists": False,
            "available_quantity": 0,
        }

    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_erp_sales_order_lines_payload(self, mock_create_erp_login):
        """Test ERP sales order line payload."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": True,
            "quantity": 5,
        }
        # Has a linked clinical order
        assert self.billable_item_1.erp_sales_order_lines_payload == {
            "sales_order": None,
            "quantity": Decimal("2"),
            "product": "a1a8a97f-1a6a-4c7d-a64f-007f3ef75072",
            "new_price": Decimal("2000"),
            "organisation": str(self.billable_item_1.organisation.id),
            "quantity_confirmed": Decimal("2"),
        }

        # No linked clinical order
        assert self.billable_item_2.erp_sales_order_lines_payload is None

    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_erp_sales_order_lines_payload_without_stock_quanity(
        self, mock_create_erp_login
    ):
        """Test ERP sales order line payload."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }
        assert self.billable_item_1.erp_sales_order_lines_payload is None

    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_erp_sales_invoice_lines_payload(self, mock_create_erp_login):
        """Test ERP sales invoice line payload."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }

        # Has a linked invoice
        assert self.billable_item_2.erp_sales_invoice_lines_payload == {
            "sales_invoice": "8522f546-4c70-465f-a9fe-ea23c0032a6b",
            "sales_order_line": None,
            "quantity": Decimal("2"),
            "product": "a1a8a97f-1a6a-4c7d-a64f-007f3ef75072",
            "pricelist_product": "fdd90a71-3ebe-444c-9a52-9aa79300a07b",
            "new_price": Decimal("2000"),
            "source_document": None,
            "organisation": str(self.billable_item_2.organisation.id),
        }

        # No linked invoice
        assert self.billable_item_1.erp_sales_invoice_lines_payload is None


class RefundModelTestCase(LoggedInMixin):
    """Test Refund Model."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.user_id_metadata = {
            "created_by": self.user.id,
            "updated_by": self.user.id,
            "department_id": "6db73406-4d24-445b-9896-564eb1a480b4",
        }
        self.patient = baker.make(
            Patient,
            customer_id="e9fe2c6a-d60d-4722-a3c3-760e9c37b8ec",
            **self.user_id_metadata,
        )
        self.queue = baker.make(Queue)
        self.visit = baker.make(
            Visit,
            patient=self.patient,
            current_queue=self.queue,
            status="ARRIVED",
            **self.user_id_metadata,
        )

    def test_sales_credit_notes_and_lines_payload(self):
        """Test syncing refund payload with the ERP."""
        invoice = Invoice.objects.latest("created")
        billable_item = baker.make(
            BillableItem,
            product_id="a1a8a97f-1a6a-4c7d-a64f-007f3ef75072",
            pricelist_product_id="bd9fa0df-052d-4157-a447-b7d04ade31db",
            clinical_order=None,
            invoice=invoice,
            quantity=5,
            price=2_000,
        )
        invoice.workflow_state = "SUBMITTED"
        invoice.save()
        invoice.refresh_from_db()
        invoice.workflow_state = "PROCESSED"
        invoice.save()
        invoice.refresh_from_db()
        assert invoice.refund_status == NOT_REFUNDED

        refund = baker.make(
            Refund,
            invoice=invoice,
            department_id=invoice.department_id,
            sales_credit_note_id="9e221ca3-7aff-4365-a745-ea168e5d361e",
            reason="Jamii waiver applied hence warrants a refund processed.",
            kra_reason_code=("10"),
        )
        refund_line = baker.make(
            RefundLine,
            refund=refund,
            invoice_line=billable_item,
            quantity=5,
            amount=Decimal(2000),
        )
        assert refund.amount == 1_0000
        assert refund.invoice.refund_status == FULLY_REFUNDED

        assert refund.erp_sales_credit_notes_payload == {
            "customer": "e9fe2c6a-d60d-4722-a3c3-760e9c37b8ec",
            "reason": "Jamii waiver applied hence warrants a refund processed.",
            "kra_reason_code": "10",
            "amount": "10000.0000",
            "invoice": str(invoice.sales_invoice_id),
            "workflow_state": "DRAFT",
            "organisation": str(refund.organisation.id),
            "source_organisation_unit": str(refund.department_id),
        }

        assert refund_line.erp_sales_credit_note_lines_payload == {
            "credit_note": "9e221ca3-7aff-4365-a745-ea168e5d361e",
            "quantity": refund_line.quantity,
            "product": str(billable_item.product_id),
            "pricelist_product": str(billable_item.pricelist_product_id),
            "new_price": billable_item.price,
            "organisation": str(billable_item.organisation.id),
        }
