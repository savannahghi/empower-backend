"""Test visits views."""
import base64
from datetime import datetime
from itertools import cycle
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker
from rest_framework import status
from rest_framework.status import HTTP_201_CREATED

from sil_advantage.billing.models import BillableItem, ClinicalOrder, Payment
from sil_advantage.common.models import Person, PersonContact
from sil_advantage.patients.models import Patient
from sil_advantage.permissions import perms
from sil_advantage.scheduling.models import Appointment
from sil_advantage.settings.models import OrganisationSetting
from sil_advantage.sil_auth.models import SILUser
from sil_advantage.visits.models import (
    Queue,
    ServiceRequest,
    Visit,
    VisitDispatch,
)
from tests.common.test_common_views import LoggedInMixin

MOCK_ROOT = "sil_advantage.visits.views."


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
class VisitViewSetTestCase(LoggedInMixin):
    """Test Visits viewset."""

    def setUp(self):
        """Set up the test environment."""
        super().setUp()

        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")

        person = baker.make(
            Person,
            first_name="Stephen",
            last_name="Mwangi",
            organisation=self.global_organisation,
        )
        person2 = baker.make(
            Person,
            first_name="Sarah",
            last_name="Njuguna",
            organisation=self.global_organisation,
        )
        baker.make(
            PersonContact,
            contact_type=iter(["phone_number", "email"]),
            contact=iter(["+254790360360", "stephen@example.com"]),
            is_primary_contact=True,
            person=person,
            organisation=self.global_organisation,
            _quantity=2,
        )
        OrganisationSetting.set_org_setting(
            self.global_organisation,
            "patients:patient_id_format",
            "SIL{file_number:03d}",
        )
        self.patient = baker.make(
            Patient,
            person=person,
            organisation=self.global_organisation,
        )
        self.patient2 = baker.make(
            Patient,
            person=person2,
            organisation=self.global_organisation,
        )
        self.queue = baker.make(Queue, name="Consultation")

    def test_create_visit(self):
        """Test creating a visit."""
        visit_data = {
            "patient": self.patient.id,
            "start": datetime(2022, 10, 29),
            "billing_class": "CASH",
            "current_queue": self.queue.id,
            "status": "ARRIVED",
            "visit_type": "AMB",
        }

        url = reverse("visit-list")
        self.client.post(
            url,
            visit_data,
            format="json",
            headers={
                "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
                "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
                "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
                "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
            },
        )
        visit = Visit.objects.latest("created")
        service_request = ServiceRequest.objects.get(visit=visit.id)
        occurrence = service_request.occurrence.strftime("%d-%m-%Y")
        self.assertEqual("29-10-2022", occurrence)

    def test_filter_with_branch_id(self):
        """Test filtering visits with branch permissions."""
        # Create a visit for a specific branch
        visit_data_1 = {
            "patient": self.patient,
            "start": datetime(2022, 10, 29),
            "billing_class": "CASH",
            "current_queue": self.queue,
            "organisation": self.global_organisation,
            "status": "FINISHED",
            "visit_type": "AMB",
            "branch_id": "9f273420-b325-475c-a1a5-83451aeb837e",
            "updated_by": uuid4(),
            "created_by": uuid4(),
        }
        Visit.objects.create(**visit_data_1)

        # Create another visit for a different branch
        visit_data_2 = {
            "patient": self.patient,
            "start": datetime(2022, 10, 29),
            "billing_class": "CASH",
            "current_queue": self.queue,
            "organisation": self.global_organisation,
            "status": "ARRIVED",
            "visit_type": "AMB",
            "branch_id": "9f273420-b325-475c-a1a5-83451aeb837f",
            "updated_by": uuid4(),
            "created_by": uuid4(),
        }
        Visit.objects.create(**visit_data_2)

        url = reverse("visit-list")
        response = self.client.get(
            url,
            format="json",
            headers={"X-Branch": "9f273420-b325-475c-a1a5-83451aeb837e"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_filter_with_branch_id_with_org_perm(self):
        """Test filtering visits with organisation permissions."""
        # Create a visit for a specific branch
        self.assign_permission([perms.ORGANISATION_ADMIN[0]])
        visit_data_1 = {
            "patient": self.patient,
            "start": datetime(2022, 10, 29),
            "billing_class": "CASH",
            "current_queue": self.queue,
            "organisation": self.global_organisation,
            "status": "FINISHED",
            "visit_type": "AMB",
            "branch_id": "9f273420-b325-475c-a1a5-83451aeb837e",
            "updated_by": uuid4(),
            "created_by": uuid4(),
        }
        Visit.objects.create(**visit_data_1)

        # Create another visit for a different branch
        visit_data_2 = {
            "patient": self.patient,
            "start": datetime(2022, 10, 29),
            "billing_class": "CASH",
            "current_queue": self.queue,
            "organisation": self.global_organisation,
            "status": "ARRIVED",
            "visit_type": "AMB",
            "branch_id": "9f273420-b325-475c-a1a5-83451aeb837f",
            "updated_by": uuid4(),
            "created_by": uuid4(),
        }
        Visit.objects.create(**visit_data_2)

        url = reverse("visit-list")
        response = self.client.get(
            url,
            format="json",
            headers={"X-Branch": "9f273420-b325-475c-a1a5-83451aeb837e"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    @patch(MOCK_ROOT + "fetch_from_erp_cache")
    def test_downloading_consolidated_invoice(
        self,
        mock_fetch_from_erp,
    ):
        """Test downloading the visit's consolidated invoice."""
        with open("tests/assets/test_image.jpeg", "rb") as f:
            logo = f"data:image/png;base64, {base64.b64encode(f.read()).decode()}"
        erp_cache = {
            "organisations": {
                "organisation_logo": {"data": logo},
                "organisation_name": "Savannah Informatics Limited",
                "physical_address": "5th Floor, One Padmore Place, Kilimani",
                "phone_number": "+2547903603630",
                "email_address": "info@savannahinformatics.com",
                "web_address": "www.savannahinformatics.com",
            },
            "clusters": {
                "orgunit_logo": {"data": logo},
                "name": "Test Cluster",
                "physical_address": "5th Floor, One Padmore Place, Kilimani",
                "phone_number": "+2547903603630",
                "email_address": "info@savannahinformatics.com",
                "use_cluster_doc_details": True,
            },
            "branches": {"name": "Kilimani"},
            "currencies": {
                "results": [
                    {
                        "iso_code": "KES",
                        "organisation": "ebef581c-494b-4772-9e49-0b0755c44e61",
                    }
                ]
            },
            "payment_methods": {
                "id": "4f026ad4-2b8e-4761-a0cc-4d174bb0dad8",
                "name": "Cash",
            },
            "customers": {
                "partner_name": "APA Insurance",
            },
        }
        mock_fetch_from_erp.side_effect = lambda r, *args, **kwargs: erp_cache[r]
        current_year = str(timezone.now().year)[2:]

        visit = baker.make(
            Visit,
            status="IN_PROGRESS",
            patient=self.patient,
            appointment=None,
            created_by=self.user.id,
            updated_by=self.user.pk,
        )

        queue = baker.make(Queue, name="Consultation")
        visit.current_queue = queue
        visit.save()
        invoice = visit.service_requests.latest("created").invoice
        invoice.sales_invoice_id = "91847399-0e82-4b40-940c-0646be24d59e"
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

        queue = baker.make(Queue, name="Pharmacy")
        visit.current_queue = queue
        visit.save()
        invoice = visit.service_requests.latest("created").invoice
        invoice.sales_invoice_id = "4662eb8f-6c1c-4c5c-b0d1-0cc5fc2b33e2"
        invoice.invoice_number = "SIL/KIL/0785"
        invoice.save()
        baker.make(
            BillableItem,
            invoice=invoice,
            name="Panadol 500mg",
            price=10,
            original_price=10,
            quantity=14,
        )
        baker.make(
            BillableItem,
            invoice=invoice,
            name=" Ablation of endometriotic spots ",
            price=1_800,
            original_price=2_000,
            quantity=1,
        )
        baker.make(
            Payment,
            invoice=invoice,
            amount=100,
            payment_method="4f026ad4-2b8e-4761-a0cc-4d174bb0dad8",
        )
        baker.make(
            Payment,
            invoice=invoice,
            amount=1500,
            payment_method="4f026ad4-2b8e-4761-a0cc-4d174bb0dad8",
        )
        year = visit.created.year
        url = reverse("visit-consolidated-invoice", kwargs={"pk": visit.pk})
        response = self.client.get(url)
        self.assertEqual(
            response.context["document_number"], f"INV/SAV/KIL/{year}/0001"
        )
        self.assertEqual(
            response.context["org_physical_address"],
            erp_cache["organisations"]["physical_address"],
        )
        self.assertEqual(
            response.context["org_phone_number"],
            erp_cache["organisations"]["phone_number"],
        )
        self.assertEqual(
            response.context["org_email_address"],
            erp_cache["organisations"]["email_address"],
        )
        self.assertEqual(
            response.context["org_web_address"],
            erp_cache["organisations"]["web_address"],
        )
        self.assertEqual(
            response.context["cluster_name"],
            erp_cache["clusters"]["name"],
        )
        self.assertEqual(
            response.context["cluster_physical_address"],
            erp_cache["clusters"]["physical_address"],
        )
        self.assertEqual(
            response.context["cluster_phone_number"],
            erp_cache["clusters"]["phone_number"],
        )
        self.assertEqual(
            response.context["cluster_email_address"],
            erp_cache["clusters"]["email_address"],
        )
        self.assertEqual(
            response.context["use_cluster_details"],
            erp_cache["clusters"]["use_cluster_doc_details"],
        )
        self.assertEqual(response.context["branch_name"], erp_cache["branches"]["name"])
        self.assertEqual(
            response.context["currency_iso_code"],
            erp_cache["currencies"]["results"][0]["iso_code"],
        )
        self.assertEqual(
            response.context["patient_name"], visit.patient.person.get_full_name()
        )
        self.assertEqual(response.context["patient_number"], visit.patient.patient_id)
        self.assertEqual(response.context["visit_number"], visit.visit_number)
        self.assertEqual(
            response.context["invoices"][0]["service_point"], "Consultation"
        )
        self.assertEqual(
            response.context["invoices"][0]["invoice_number"], "SIL/KIL/0782"
        )
        self.assertEqual(
            response.context["payer_name"], erp_cache["customers"]["partner_name"]
        )

        self.assertEqual(
            response.context["invoices"][0]["lines"][0]["product_name"],
            "General Consultation",
        )
        self.assertEqual(response.context["invoices"][1]["service_point"], "Pharmacy")
        self.assertEqual(
            response.context["invoices"][1]["invoice_number"], "SIL/KIL/0785"
        )
        self.assertEqual(
            response.context["invoices"][1]["lines"][0]["product_name"],
            "Panadol 500mg",
        )
        self.assertEqual(
            response.context["invoices"][1]["lines"][1]["product_name"],
            " Ablation of endometriotic spots ",
        )
        self.assertEqual(
            response.context["invoices"][1]["payment_methods"]["Cash"], 1_600
        )
        assert response.headers["content-disposition"] == (
            f"attachment; filename=Visit 0001/{current_year} Invoice.pdf"
        )

    @patch("sil_advantage.billing.models.Invoice._perform_operation_on_erp")
    @patch("sil_advantage.visits.tasks.get_erp_client")
    def test_closing_a_visit_invoice_has_lines(
        self, mock_create_erp_login, mock_perform_operation_on_erp
    ):
        """Test closing a visit (invoice has lines)."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_perform_operation_on_erp.return_value = None
        mock_erp.inventory_operations.get_with.return_value = {
            "id": "b3719959-1bd1-43fd-9bb5-7d5b0d1ce0dd",
            "workflow_state": "DRAFT",
            "source_document": "91847399-0e82-4b40-940c-0646be24d59e",
        }
        queue = baker.make(Queue)
        visit = baker.make(Visit, status="IN_PROGRESS", current_queue=queue)
        assert visit.end is None
        service_request = ServiceRequest.objects.latest("created")
        order = ClinicalOrder.objects.latest("created")
        invoice = service_request.invoice
        invoice.sales_invoice_id = "d728a5c8-52fa-4b53-9e56-77c9527d7e14"
        invoice.save()
        order.sales_order_id = "91847399-0e82-4b40-940c-0646be24d59e"
        order.save()
        baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_500,
            original_price=1_500,
            quantity=1,
        )
        assert invoice.workflow_state == "DRAFT"
        baker.make(
            Payment,
            invoice=invoice,
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
        )

        url = reverse("visit-close", kwargs={"pk": visit.pk})
        self.client.post(url, data={})
        mock_erp.sales_invoices.transition.assert_called_once_with(
            UUID("d728a5c8-52fa-4b53-9e56-77c9527d7e14"),
            "DRAFT_SUBMIT_APPROVE",
        )
        mock_erp.sales_orders.transition.assert_called_once_with(
            UUID("91847399-0e82-4b40-940c-0646be24d59e"),
            "DRAFT_SUBMIT_APPROVE",
        )
        mock_erp.payment_receipts.transition.assert_called_once_with(
            UUID("58ebc4b3-c088-4a76-9c4e-d112c801ae4c"),
            "DRAFT_SUBMIT_APPROVE",
        )
        mock_erp.inventory_operations.auto_process_inventory.assert_called_once_with(
            "b3719959-1bd1-43fd-9bb5-7d5b0d1ce0dd",
        )

        visit.refresh_from_db()
        assert visit.status == "FINISHED"
        assert visit.end is not None
        invoice = visit.service_requests.first().invoice
        order = visit.service_requests.first().clinical_order
        assert invoice.workflow_state == "PROCESSED"
        assert order.workflow_state == "PROCESSED"

    @patch("sil_advantage.billing.models.Invoice._perform_operation_on_erp")
    @patch("sil_advantage.visits.tasks.get_erp_client")
    def test_closing_a_visit_auto_process_inventory_timeouts(
        self,
        mock_create_erp_login,
        mock_perform_operation_on_erp,
    ):
        """Test closing a visit (invoice has lines)."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_perform_operation_on_erp.return_value = None
        mock_erp.inventory_operations.get_with.return_value = {
            "id": "b3719959-1bd1-43fd-9bb5-7d5b0d1ce0dd",
            "workflow_state": "DRAFT",
            "source_document": "91847399-0e82-4b40-940c-0646be24d59e",
        }
        mock_erp.inventory_operations.auto_process_inventory.side_effect = Exception(
            "Error!"
        )
        queue = baker.make(Queue)
        visit = baker.make(Visit, status="IN_PROGRESS", current_queue=queue)
        assert visit.end is None
        service_request = ServiceRequest.objects.latest("created")
        order = ClinicalOrder.objects.latest("created")
        invoice = service_request.invoice
        invoice.sales_invoice_id = "d728a5c8-52fa-4b53-9e56-77c9527d7e14"
        invoice.save()
        order.sales_order_id = "91847399-0e82-4b40-940c-0646be24d59e"
        order.save()
        baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_500,
            original_price=1_500,
            quantity=1,
        )
        assert invoice.workflow_state == "DRAFT"
        baker.make(
            Payment,
            invoice=invoice,
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
        )

        url = reverse("visit-close", kwargs={"pk": visit.pk})
        self.client.post(url, data={})
        mock_erp.sales_invoices.transition.assert_called_once_with(
            UUID("d728a5c8-52fa-4b53-9e56-77c9527d7e14"),
            "DRAFT_SUBMIT_APPROVE",
        )
        mock_erp.sales_orders.transition.assert_called_once_with(
            UUID("91847399-0e82-4b40-940c-0646be24d59e"),
            "DRAFT_SUBMIT_APPROVE",
        )
        mock_erp.payment_receipts.transition.assert_called_once_with(
            UUID("58ebc4b3-c088-4a76-9c4e-d112c801ae4c"),
            "DRAFT_SUBMIT_APPROVE",
        )
        mock_erp.inventory_operations.auto_process_inventory.assert_called_once_with(
            "b3719959-1bd1-43fd-9bb5-7d5b0d1ce0dd",
        )

        visit.refresh_from_db()
        assert visit.status == "FINISHED"
        assert visit.end is not None
        invoice = visit.service_requests.first().invoice
        order = visit.service_requests.first().clinical_order
        assert invoice.workflow_state == "PROCESSED"
        assert order.workflow_state == "PROCESSED"

    @patch("sil_advantage.visits.tasks.get_erp_client")
    def test_closing_a_visit_invoice_has_no_lines(self, mock_create_erp_login):
        """Test closing a visit (invoice has no lines)."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp

        queue = baker.make(Queue)
        visit = baker.make(Visit, status="IN_PROGRESS", current_queue=queue)
        assert visit.end is None

        order = ClinicalOrder.objects.latest("created")
        invoice = visit.service_requests.first().invoice
        invoice.sales_invoice_id = "d728a5c8-52fa-4b53-9e56-77c9527d7e14"
        invoice.save()
        order.sales_order_id = "91847399-0e82-4b40-940c-0646be24d59e"
        order.save()
        assert invoice.workflow_state == "DRAFT"

        url = reverse("visit-close", kwargs={"pk": visit.pk})
        self.client.post(url, data={})

        mock_erp.sales_invoices.transition.assert_called_once_with(
            UUID("d728a5c8-52fa-4b53-9e56-77c9527d7e14"),
            "DRAFT_CLOSED",
        )
        mock_erp.sales_orders.transition.assert_called_once_with(
            UUID("91847399-0e82-4b40-940c-0646be24d59e"),
            "DRAFT_CLOSED",
        )

        visit.refresh_from_db()
        assert visit.status == "FINISHED"
        assert visit.end is not None
        invoice = visit.service_requests.first().invoice
        assert invoice.workflow_state == "CLOSED"
        order = visit.service_requests.first().clinical_order
        assert order.workflow_state == "CLOSED"

    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_closing_a_credit_visit_create_visit_dispatch(self, mock_create_erp_login):
        """Test closing a credit visit creates a visit dispatch instance."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }

        queue = baker.make(Queue)
        visit = baker.make(
            Visit, status="IN_PROGRESS", billing_class="CREDIT", appointment=None
        )
        assert visit.end is None

        baker.make(ServiceRequest, visit=visit, queue=queue)
        invoice = visit.service_requests.first().invoice
        invoice.sales_invoice_id = "d728a5c8-52fa-4b53-9e56-77c9527d7e14"
        invoice.save()
        baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_500,
            original_price=1_500,
            quantity=1,
        )
        assert invoice.workflow_state == "DRAFT"
        baker.make(
            Payment,
            invoice=invoice,
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
        )

        url = reverse("visit-close", kwargs={"pk": visit.pk})
        self.client.post(url, data={})

        visit.refresh_from_db()
        assert visit.status == "FINISHED"
        # assert billing class
        assert visit.billing_class == "CREDIT"
        # assert visit dispatch creation
        visit_dispatch = VisitDispatch.objects.get(visit=visit)
        assert visit_dispatch.status == "DRAFT"
        assert visit_dispatch.organisation == visit.organisation

    @patch("sil_advantage.common.api_clients.erp.get_erp_client")
    def test_closing_a_cash_visit_no_visit_dispatch(self, mock_create_erp_login):
        """Test closing a cash visit no visitdispatch instance created."""
        mock_erp = MagicMock()
        mock_create_erp_login.return_value = mock_erp
        mock_erp.stockquantity.check_stock_quantity.return_value = {
            "stock_quantity_exists": False,
            "quantity": 0,
        }
        queue = baker.make(Queue)
        visit = baker.make(
            Visit, status="IN_PROGRESS", billing_class="CASH", appointment=None
        )
        assert visit.end is None

        baker.make(ServiceRequest, visit=visit, queue=queue)
        invoice = visit.service_requests.first().invoice
        invoice.sales_invoice_id = "d728a5c8-52fa-4b53-9e56-77c9527d7e14"
        invoice.save()
        baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_500,
            original_price=1_500,
            quantity=1,
        )
        assert invoice.workflow_state == "DRAFT"
        baker.make(
            Payment,
            invoice=invoice,
            payment_receipt_id="58ebc4b3-c088-4a76-9c4e-d112c801ae4c",
            organisation=invoice.organisation,
        )

        url = reverse("visit-close", kwargs={"pk": visit.pk})
        self.client.post(url, data={})

        visit.refresh_from_db()
        assert visit.status == "FINISHED"
        # assert billing class
        assert visit.billing_class == "CASH"
        # assert visit dispatch is not created for cash visits
        visit_dispatch_exists = VisitDispatch.objects.filter(visit=visit).exists()
        self.assertFalse(visit_dispatch_exists)

    def test_status_transition(self):
        """Test status transition using sil_transitions."""
        appt_start = timezone.now() + timezone.timedelta(minutes=60)
        appt_end = appt_start + timezone.timedelta(minutes=60)
        appointment = baker.make(
            Appointment,
            appointment_status="BOOKED",
            start=appt_start,
            end=appt_end,
            slot__schedule__slot_duration=60,
            slot__start=appt_start,
            slot__end=appt_end,
        )
        visit = baker.make(Visit, status="ARRIVED", appointment=appointment)

        url = reverse("visit-transition", kwargs={"id": visit.pk, "status": "TRIAGED"})
        self.client.patch(url)

        visit.refresh_from_db()
        assert visit.status == "TRIAGED"
        appointment.refresh_from_db()
        assert appointment.appointment_status == "ARRIVED"

        url = reverse(
            "visit-transition",
            kwargs={"id": visit.pk, "status": "IN_PROGRESS"},
        )
        self.client.patch(url)

        appointment.refresh_from_db()
        assert appointment.appointment_status == "FULFILLED"

    def test_filter_by_multiple_visit_statuses(self):
        """Test filter by multiple visit statuses."""
        baker.make(
            Visit,
            status=cycle(
                [
                    "ARRIVED",
                    "IN_PROGRESS",
                    "FINISHED",
                    "ON_LEAVE",
                    "CANCELLED",
                ]
            ),
            _quantity=7,
        )
        visit = baker.make(Visit, status="FINISHED", patient=self.patient)
        baker.make(ServiceRequest, visit=visit)

        visit_list_url = reverse("visit-list")

        # no filter
        results = self.client.get(visit_list_url).json()
        assert results["count"] == 8

        # 1 filter
        results = self.client.get(visit_list_url + "?status=ARRIVED").json()
        assert results["count"] == 2
        self.assertCountEqual(
            [visit["status"] for visit in results["results"]],
            ["ARRIVED", "ARRIVED"],
        )

        # 3 filters
        results = self.client.get(
            visit_list_url + "?status=ARRIVED,CANCELLED,FINISHED"
        ).json()
        assert results["count"] == 5
        self.assertCountEqual(
            [visit["status"] for visit in results["results"]],
            ["ARRIVED", "ARRIVED", "CANCELLED", "FINISHED", "FINISHED"],
        )

    @patch(MOCK_ROOT + "fetch_from_erp_cache")
    def test_open_invoice_endpoint_invalid_token(self, mock_fetch_from_erp):
        """Test opening a patient's invoice with an invalid token."""
        url = reverse("visit-open-invoice")
        response = self.client.get(f"{url}?t=invalid_token")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"error": "Invalid token"})

    @patch(MOCK_ROOT + "fetch_from_erp_cache")
    def test_open_invoice_endpoint(self, mock_fetch_from_erp):
        """Test opening a patient's invoice based on the token."""
        erp_cache = {
            "organisations": {
                "organisation_logo": {"data": ""},
                "organisation_name": "Savannah Informatics Limited",
                "physical_address": "5th Floor, One Padmore Place, Kilimani",
                "phone_number": "+2547903603630",
                "email_address": "info@savannahinformatics.com",
                "web_address": "www.savannahinformatics.com",
            },
            "clusters": {
                "orgunit_logo": {"data": ""},
                "name": "Test Cluster",
                "physical_address": "5th Floor, One Padmore Place, Kilimani",
                "phone_number": "+2547903603630",
                "email_address": "info@savannahinformatics.com",
                "use_cluster_doc_details": True,
            },
            "branches": {"name": "Kilimani"},
            "currencies": {
                "results": [
                    {
                        "iso_code": "KES",
                        "organisation": "ebef581c-494b-4772-9e49-0b0755c44e61",
                    }
                ]
            },
            "customers": {
                "partner_name": "APA Insurance",
            },
            "payment_methods": {
                "id": "4f026ad4-2b8e-4761-a0cc-4d174bb0dad8",
                "name": "Cash",
            },
        }
        mock_fetch_from_erp.side_effect = lambda r, *args, **kwargs: erp_cache[r]
        baker.make(
            Visit,
            post_visit_survey_token="8tjjTKHd",
            patient=self.patient,
            created_by=self.user.id,
            updated_by=self.user.pk,
        )

        url = reverse("visit-open-invoice")
        response = self.client.get(f"{url}?t=8tjjTKHd")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue("Content-Disposition" in response.headers)

    @patch("sil_advantage.visits.views.VisitViewSet.generate_invoice_content")
    def test_open_invoice_exception_handling(self, mock_generate_invoice_content):
        """Test exception handling in open_invoice method."""
        mock_generate_invoice_content.side_effect = Exception(
            "Unexpected error occured"
        )

        valid_token = "8tjjTKHd"
        baker.make(
            Visit,
            post_visit_survey_token=valid_token,
            patient=self.patient,
            created_by=self.user.id,
            updated_by=self.user.pk,
        )

        url = reverse("visit-open-invoice")
        response = self.client.get(f"{url}?t={valid_token}")

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data, {"error": "Unexpected error occured"})

    def test_visit_id_success(self):
        """Test return of visit id via invoice number."""
        visit = baker.make(Visit)
        service_request = baker.make(ServiceRequest, visit=visit)
        url = reverse("visit-visit-id")
        response = self.client.get(url, {"service_request_id": service_request.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), str(visit.id))

    @patch("sil_advantage.billing.models.Invoice._perform_operation_on_erp")
    @patch("sil_advantage.visits.utils.update_state_transition")
    @patch("sil_advantage.visits.tasks.get_erp_client")
    def test_update_state_transition(
        self,
        mock_create_erp_login,
        mock_update_state_transition,
        mock_perform_operation_on_erp,
    ):
        """Test update_state_transition applies correct workflow states."""
        mock_perform_operation_on_erp.return_value = None
        queue = baker.make(Queue)
        visit = baker.make(Visit, status="IN_PROGRESS", current_queue=queue)
        assert visit.end is None
        clinical_order = ClinicalOrder.objects.latest("created")
        invoice = visit.service_requests.first().invoice
        invoice.sales_invoice_id = str(uuid4())
        invoice.save()
        clinical_order.sales_order_id = str(uuid4())
        clinical_order.save()
        baker.make(
            BillableItem,
            invoice=invoice,
            name="General Consultation",
            price=1_500,
            original_price=1_500,
            quantity=1,
        )
        assert invoice.workflow_state == "DRAFT"
        assert clinical_order.workflow_state == "DRAFT"
        baker.make(
            Payment,
            invoice=invoice,
            payment_receipt_id=str(uuid4()),
            organisation=invoice.organisation,
        )

        url = reverse("visit-close", kwargs={"pk": visit.pk})
        self.client.post(url, data={})
        visit.refresh_from_db()
        assert visit.status == "FINISHED"
        invoice = visit.service_requests.first().invoice
        order = visit.service_requests.first().clinical_order
        assert invoice.workflow_state == "PROCESSED"
        assert order.workflow_state == "PROCESSED"


class SurveyResponseViewSetTestCase(LoggedInMixin):
    """Test SurveyResponse viewset."""

    def test_getting_form(self):
        """Test getting the survey form template."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")

        OrganisationSetting.set_org_setting(
            self.global_organisation,
            "visits:post_visit_survey_template",
            [{"foo": "bar"}],
        )

        visit = baker.make(
            Visit,
            status="FINISHED",
            post_visit_survey_token="8tjjTKHd",
            organisation=self.global_organisation,
        )

        self.client.logout()

        form = self.client.get(
            reverse("surveyresponse-form") + "?t=8tjjTKHd",
        ).json()
        assert form == {
            "template": [{"foo": "bar"}],
            "visit": {
                "id": str(visit.id),
                "organisation_id": "ebef581c-494b-4772-9e49-0b0755c44e61",
            },
            "already_filled": False,
        }

        response = self.client.post(
            reverse("surveyresponse-list"),
            data={
                "visit": visit.id,
                "organisation": "ebef581c-494b-4772-9e49-0b0755c44e61",
                "response": {"foo": "bar"},
            },
        )
        assert response.status_code == HTTP_201_CREATED

        form = self.client.get(
            reverse("surveyresponse-form") + "?t=8tjjTKHd",
        ).json()
        assert form == {
            "template": [{"foo": "bar"}],
            "visit": {
                "id": str(visit.id),
                "organisation_id": "ebef581c-494b-4772-9e49-0b0755c44e61",
            },
            "already_filled": True,
        }
