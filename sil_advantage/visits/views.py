"""Visits views."""
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.template import loader
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import UpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.settings import api_settings, import_from_string
from sil_transitions.views import TransitionViewMixin
from weasyprint import HTML

from sil_advantage.billing.models import Invoice
from sil_advantage.common.api_clients.erp import fetch_from_erp_cache
from sil_advantage.common.filters import common_filters
from sil_advantage.common.models import InstanceHistory
from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.common.views.base import (
    CacheableBaseView,
    LenientAnonThrottle,
)
from sil_advantage.permissions import perms, scopes
from sil_advantage.settings.models import OrganisationSetting
from sil_advantage.sil_auth.permission_classes import (
    OrganisationIsActive,
    ViewBasePermission,
    WriteOnlyPermission,
)
from sil_advantage.visits import filters, models, serializers, tasks
from sil_advantage.visits.utils import generate_document_number

"""Append the default_filter_backends from settings.py to the filter backend."""
default_filter_backends = [
    import_from_string(backend, "DEFAULT_FILTER_BACKENDS")
    if isinstance(backend, str)
    else backend
    for backend in api_settings.DEFAULT_FILTER_BACKENDS
]
filter_backends = [common_filters.BranchFilterBackend] + default_filter_backends


class VisitViewSet(CacheableBaseView):
    """Viewset for Visits."""

    permissions = {
        "GET": [perms.VISIT_VIEW],
        "POST": [perms.VISIT_CREATE],
        "PATCH": [perms.VISIT_EDIT],
        "DELETE": [perms.VISIT_DELETE],
    }
    scopes = {
        "GET": [scopes.VISIT_READ],
        "POST": [scopes.VISIT_WRITE],
        "PATCH": [scopes.VISIT_WRITE],
        "DELETE": [scopes.VISIT_WRITE],
    }

    queryset = models.Visit.objects.all().prefetch_related(
        "patient__person__person_contacts"
    )
    _select_related = ["patient__person"]
    _prefetch_related = [
        "service_requests__queue",
        "service_requests__invoice__payments",
        "service_requests__invoice__refunds",
        "service_requests__invoice__invoice_lines",
    ]
    serializer_class = serializers.VisitSerializer
    filter_backends = filter_backends
    filterset_class = filters.VisitFilter
    ordering_fields = ("updated",)
    search_fields = (
        "patient__person__first_name",
        "patient__person__last_name",
        "patient__person__other_names",
        "patient__person__person_contacts__contact",
        "patient__file_number",
        "patient__person__person_ids__id_value",
    )

    _data_partition_field = "branch_id"

    def generate_invoice_content(
        self, visit: models.Visit, output_format: Optional[str] = "pdf"
    ) -> Tuple[Dict[str, Any], HttpResponse]:
        """Generate content for the consolidated invoice."""
        org = fetch_from_erp_cache(
            "organisations",
            "get",
            visit.organisation_id,
        )
        branch = fetch_from_erp_cache(
            "branches",
            "get",
            visit.branch_id,
        )
        cluster = fetch_from_erp_cache(
            "clusters",
            "get",
            visit.cluster_id,
        )
        currencies = fetch_from_erp_cache(
            "currencies",
            "list",
            filters={"organisation": str(visit.organisation_id), "is_default": True},
        )
        customer = fetch_from_erp_cache(
            "customers",
            "get",
            visit.guarantor_id,
        )
        patient_contact = visit.patient.person.phone_number or ""
        patient_contact = patient_contact[:7] + "*****" + patient_contact[12:]
        assert visit.created_by is not None
        served_by = get_user_model().objects.get(
            Q(pk=visit.created_by) | Q(guid=visit.created_by)
        )
        # Generate document number from the visit number
        document_prefix = "INV"
        organisation_name = org["organisation_name"]
        branch_name = branch["name"]
        seq = visit.visit_number.split("/")[0]
        year = visit.created.year

        setting = OrganisationSetting.get_org_setting(
            visit.organisation, "visit:document_number_format"
        )
        document_number = generate_document_number(
            setting.value,
            document_prefix,
            organisation_name,
            branch_name,
            year,
            seq,
        )
        context = {
            # metadata
            "created": visit.created,
            "generated": timezone.now(),
            "served_by": served_by.full_name,
            "document_number": document_number,
            # organisation
            "org_logo": org["organisation_logo"]["data"]
            if org.get("organisation_logo")
            else None,
            "org_name": org["organisation_name"],
            "org_physical_address": org["physical_address"],
            "org_phone_number": org["phone_number"],
            "org_email_address": org["email_address"],
            "org_web_address": org["web_address"],
            # cluster
            "cluster_logo": cluster["orgunit_logo"]["data"]
            if cluster.get("orgunit_logo")
            else None,
            "cluster_name": cluster["name"],
            "cluster_physical_address": cluster["physical_address"],
            "cluster_phone_number": cluster["phone_number"],
            "cluster_email_address": cluster["email_address"],
            "use_cluster_details": cluster["use_cluster_doc_details"],
            # branch
            "branch_name": branch["name"],
            # patient
            "patient_name": visit.patient.person.get_full_name(),
            "patient_number": visit.patient.patient_id,
            "payer_name": customer["partner_name"],
            "patient_contact": patient_contact,
            # visit
            "visit_number": visit.visit_number,
            # invoices
            "invoices": [],
            "grand_total": 0,
            "total_discounts": 0,
            # payments
            "total_paid_amount": 0,
            "total_balance": 0,
            "payment_methods": {},
            # currency
            "currency_iso_code": currencies["results"][0]["iso_code"],
        }
        total_paid_amount: Decimal = Decimal("0")
        payment_methods: Dict[str, Decimal] = {}

        for srq in visit.service_requests.all():
            invoice = srq.invoice
            lines = []
            paid_amount = invoice.amount_paid
            total_paid_amount += paid_amount

            for payment in invoice.payments.all():
                payment_method = fetch_from_erp_cache(
                    "payment_methods", "get", id=payment.payment_method
                )
                payment_method_name = payment_method.get("name")
                payment_amount = payment.amount
                if payment_method_name in payment_methods:
                    payment_methods[payment_method_name] += payment_amount
                else:
                    payment_methods[payment_method_name] = payment_amount

            for line in invoice.invoice_lines.all():
                discount = line.quantity * (line.original_price - line.price)
                line_total = line.price * line.quantity
                lines.append(
                    {
                        "product_name": line.name,
                        "price": line.price,
                        "original_price": line.original_price,
                        "quantity": line.quantity,
                        "discount": discount,
                        "total": line_total,
                    }
                )
                context["total_discounts"] += discount
                context["grand_total"] += line_total

            context["invoices"].append(
                {
                    "service_point": srq.queue.name,
                    "invoice_number": invoice.invoice_number,
                    "lines": lines,
                    "paid_amount": paid_amount,
                    "balance": invoice.amount_due - paid_amount,
                    "payment_methods": payment_methods,
                }
            )

        context["total_paid_amount"] = total_paid_amount
        context["total_balance"] = context["grand_total"] - total_paid_amount
        context["payment_methods"] = payment_methods

        template = loader.get_template("consolidated_invoice.html")
        html = template.render(context)

        response = HttpResponse(content_type="application/pdf")
        file_name = f"Visit {visit.visit_number} Invoice.pdf"
        response["Content-Disposition"] = f"attachment; filename={file_name}"
        HTML(string=html, base_url=self.request.build_absolute_uri()).write_pdf(
            response
        )
        return context, response

    @action(detail=True, methods=["GET"])
    def consolidated_invoice(
        self,
        request: AuthenticatedRequest,
        pk: UUID,
    ) -> HttpResponse:
        """Generate an invoice that consolidates lines from all invoices."""
        select_related = models.Visit.objects.select_related(
            "patient",
            "patient__person",
            "organisation",
        )

        prefetch_related = select_related.prefetch_related(
            "patient__person__person_contacts",
            "patient__person__person_ids",
            "service_requests",
            "service_requests__invoice",
            "service_requests__invoice__invoice_lines",
        )

        visit = prefetch_related.get(pk=pk)

        context, response = self.generate_invoice_content(visit)
        return response

    @action(
        detail=False,
        methods=["GET"],
        permission_classes=[AllowAny],
        throttle_classes=(LenientAnonThrottle,),
    )
    def open_invoice(self, request: Request) -> HttpResponse:
        """Open the patient's invoice based on the token."""
        token = request.GET.get("t", None)

        try:
            visit = models.Visit.objects.get(
                post_visit_survey_token=token,
            )
        except models.Visit.DoesNotExist:
            return Response(
                {"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            context, response = self.generate_invoice_content(visit)
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return response

    @action(detail=True, methods=["POST"])
    def close(self, request: AuthenticatedRequest, pk: UUID) -> Response:
        """Complete/Close the visit."""
        visit: models.Visit = self.get_object()
        visit.status = "FINISHED"
        visit.end = timezone.now()
        visit.save(update_fields=["status", "end"])

        # Check if billing class is credit and create a VisitDispatch instance
        if visit.billing_class == "CREDIT":
            user = request.user
            models.VisitDispatch.objects.create(
                status="DRAFT",
                date_added=timezone.now().date(),
                visit=visit,
                organisation=visit.organisation,
                created_by=user.guid,
                updated_by=user.guid,
            )
        # make sure we close all service requests as well
        for service_request in (
                visit.service_requests.filter(
                    status__in=(
                            "PENDING",
                            "WAITING",
                            "IN_PROGRESS",
                            "COMPLETED",
                    )
                ).only("id", "status").order_by("created")
        ):  # fmt: skip
            service_request.status = "COMPLETED"
            service_request.save(update_fields=["status"])
            tasks.close_service_request.apply_async(
                queue=settings.CELERY_DEFAULT_QUEUE,
                priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
                args=(service_request.id,),
            )

        data = serializers.VisitSerializer(visit).data
        return Response(data)

    @action(
        detail=False,
        methods=["GET"],
    )
    def visit_id(self, request: Request) -> HttpResponse:
        """Return a visit id through invoice number."""
        invoice_number = request.GET.get("invoice_number", None)
        invoice = Invoice.objects.get(invoice_number=invoice_number)
        service_request = invoice.service_request
        visit_id = service_request.visit.id
        return Response(visit_id, status=status.HTTP_200_OK)


class VisitTransitionView(TransitionViewMixin, UpdateAPIView):
    """VisitTransition API View."""

    permissions = {
        "GET": [perms.VISIT_VIEW],
        "POST": [perms.VISIT_CREATE],
        "PATCH": [perms.VISIT_EDIT],
        "DELETE": [perms.VISIT_DELETE],
    }
    scopes = {
        "GET": [scopes.VISIT_READ],
        "POST": [scopes.VISIT_WRITE],
        "PATCH": [scopes.VISIT_WRITE],
        "DELETE": [scopes.VISIT_WRITE],
    }
    queryset = models.Visit.objects.all()
    permission_classes = (IsAuthenticated & ViewBasePermission & OrganisationIsActive,)
    serializer_class = serializers.VisitSerializer
    lookup_field = "id"
    transition_graph = models.VISIT_STATUS_TRANSITION_GRAPH
    transition_field = "status"
    transition_log_serializer = serializers.VisitTransitionLogSerializer

    _data_partition_field = "branch_id"


class QueueViewSet(CacheableBaseView):
    """Viewset for Queues."""

    permissions = {
        "GET": [perms.QUEUE_VIEW],
        "POST": [perms.QUEUE_CREATE],
        "PATCH": [perms.QUEUE_EDIT],
        "DELETE": [perms.QUEUE_DELETE],
    }
    scopes = {
        "GET": [scopes.QUEUE_READ],
        "POST": [scopes.QUEUE_WRITE],
        "PATCH": [scopes.QUEUE_WRITE],
        "DELETE": [scopes.QUEUE_WRITE],
    }

    queryset = (
        models.Queue.objects.all()
        .prefetch_related(
            Prefetch(
                "active_visits",
                queryset=(
                    models.Visit.objects.all()
                    .only("id", "current_queue_id")
                )
            )
        )
    )  # fmt: skip
    serializer_class = serializers.QueueSerializer

    filterset_class = filters.QueueFilter
    ordering_fields = (
        "updated",
        "name",
    )
    search_fields: list[str] = ["name"]

    _data_partition_field = "organisation"


class ServiceRequestViewSet(CacheableBaseView):
    """Viewset for Service Requests."""

    permissions = {
        "GET": [perms.VISIT_VIEW],
        "POST": [perms.VISIT_CREATE],
        "PATCH": [perms.VISIT_EDIT],
        "DELETE": [perms.VISIT_DELETE],
    }
    scopes = {
        "GET": [scopes.VISIT_READ],
        "POST": [scopes.VISIT_WRITE],
        "PATCH": [scopes.VISIT_WRITE],
        "DELETE": [scopes.VISIT_WRITE],
    }

    queryset = models.ServiceRequest.objects.all().prefetch_related(
        "visit__patient__person__person_contacts"
    )
    _select_related = [
        "invoice",
        "queue",
        "visit__patient__person",
    ]
    _prefetch_related = [
        "invoice__payments",
        "invoice__refunds",
        "invoice__invoice_lines",
    ]
    serializer_class = serializers.ServiceRequestSerializer

    filterset_class = filters.ServiceRequestFilter
    ordering_fields = ("updated", "created")

    search_fields: list[str] = [
        "queue__name",
        "queue__queue_type",
        "visit__patient__person__first_name",
        "visit__patient__person__last_name",
    ]

    _data_partition_field = "branch_id"

    export_fields = {
        "invoice.invoice_number": {"label": "Invoice Number"},
        "invoice.created": {
            "label": "Invoice Date",
        },
        "patient_name": {
            "label": "Patient Name",
        },
        "invoice.amount_due": {
            "label": "Amount Due",
        },
        "invoice.amount_paid": {
            "label": "Amount Paid",
        },
    }


class SurveyResponseViewSet(CacheableBaseView):
    """Viewset for survey responses."""

    permission_classes: tuple = (
        WriteOnlyPermission
        | (IsAuthenticated & ViewBasePermission & OrganisationIsActive),
    )

    permissions = {
        "GET": [perms.VISIT_VIEW],
        "POST": [],
        "PATCH": [perms.VISIT_EDIT],
        "DELETE": [perms.VISIT_DELETE],
    }
    scopes = {
        "GET": [scopes.VISIT_READ],
        "POST": [],
        "PATCH": [scopes.VISIT_WRITE],
        "DELETE": [scopes.VISIT_WRITE],
    }

    queryset = models.SurveyResponse.objects.all()
    serializer_class = serializers.SurveyResponseSerializer

    filterset_class = filters.SurveyResponseFilter
    ordering_fields = ("updated",)
    search_fields: list[str] = []

    _data_partition_field = "branch_id"

    @action(
        detail=False,
        methods=["GET"],
        permission_classes=[AllowAny],
        throttle_classes=(LenientAnonThrottle,),
    )
    def form(self, request: Request) -> Response:
        """Return the survey form template."""
        token = request.GET.get("t", None)
        visit = models.Visit.objects.get(
            post_visit_survey_token=token,
        )

        org = visit.organisation
        current_template = OrganisationSetting.get_org_setting(
            org,
            "visits:post_visit_survey_template",
        )

        template_as_of_visit = InstanceHistory.as_of(
            OrganisationSetting,
            current_template.id,
            visit.created,
        )

        template = template_as_of_visit or current_template.preference
        data = {
            "template": template,
            "visit": {
                "id": visit.id,
                "organisation_id": visit.organisation.id,
            },
            "already_filled": models.SurveyResponse.objects.filter(
                visit=visit
            ).exists(),
        }

        return Response(data)
