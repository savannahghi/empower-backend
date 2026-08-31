"""Visits tasks."""
import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

from celery.schedules import crontab
from django.conf import settings
from django.template import loader
from django.utils import timezone as django_timezone
from xxhash import xxh128

from sil_advantage.billing.utils import get_wallet_balances
from sil_advantage.common.api_clients import get_erp_client
from sil_advantage.common.models import Organisation
from sil_advantage.common.tasks import BaseTaskWithRetry
from sil_advantage.common.utilities.cube import CubeJS
from sil_advantage.config import celery_app
from sil_advantage.notifications.email import send_email
from sil_advantage.notifications.models import Group
from sil_advantage.settings.models import OrganisationSetting
from sil_advantage.visits.models import QUEUE_TYPES, ServiceRequest, Visit
from sil_advantage.visits.utils import (
    send_post_visit_survey_sms,
    send_visit_summary_sms,
    update_state_transition,
)

LOGGER = logging.getLogger(__name__)


@celery_app.on_after_finalize.connect
def setup_periodic_tasks(**kwargs: Any) -> None:
    """Register the periodic tasks with Celery.

    Args:
        **kwargs: Arbitrary keyword arguments.
    """
    celery_app.add_periodic_task(
        crontab(hour=7, minute=30),
        dispatch_daily_reports,
        name="dispatch-daily-reports",
        priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
    )


@celery_app.task(base=BaseTaskWithRetry)
def dispatch_daily_reports() -> None:
    """Dispatch daily billing reports.

    This task basically triggers `send_daily_report_for_org`
    for all organisations we have. This happens asynchronously
    to isolate errors and increase throughput to workers.
    """
    orgs = Organisation.objects.filter(active=True).only("slade_code")
    for org in orgs.iterator():
        send_daily_report_for_org.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_LOW_PRIORITY,
            args=(org.slade_code,),
        )


@celery_app.task(base=BaseTaskWithRetry)
def send_daily_report_for_org(
    slade_code: int,
) -> None:
    """Send daily report for one organisation."""
    message_group = Group.objects.filter(
        organisation__slade_code=slade_code,
        role="DAILY_DIGEST",
    ).select_related("organisation")
    if message_group.exists():
        group = message_group.latest("updated")
        to = group.email_recipients
        org = group.organisation
    else:
        LOGGER.warning(
            f"Org {slade_code} has no recipients for the daily stats email report."
        )
        return

    cube_js = CubeJS(slade_code)
    queries = {
        "patients_new_count": {
            "measures": ["PatientSummaryMart.count"],
            "timeDimensions": [
                {
                    "dimension": "PatientSummaryMart.createdDate",
                    "granularity": "day",
                    "dateRange": "Yesterday",
                }
            ],
            "order": {"PatientSummaryMart.createdDate": "asc"},
        },
        "visits_started_count": {
            "measures": ["AdvantageVisitsMart.count"],
            "timeDimensions": [
                {
                    "dimension": "AdvantageVisitsMart.visitStartDate",
                    "granularity": "day",
                    "dateRange": "Yesterday",
                }
            ],
            "order": {"AdvantageVisitsMart.visitStartDate": "asc"},
        },
        "total_discount_amount": {
            "filters": [
                {
                    "member": "AdvantageInvoiceLinesMart.discount",
                    "operator": "gt",
                    "values": ["0"],
                },
                {
                    "member": "AdvantageInvoiceLinesMart.price",
                    "operator": "gt",
                    "values": ["0"],
                },
            ],
            "measures": [
                "AdvantageInvoiceLinesMart.totalDiscount",
            ],
            "timeDimensions": [
                {
                    "dimension": "AdvantageInvoiceLinesMart.invoiceDate",
                    "granularity": "day",
                    "dateRange": "Yesterday",
                }
            ],
        },
        "total_waived_amount": {
            "filters": [
                {
                    "member": "AdvantageInvoiceLinesMart.discount",
                    "operator": "gt",
                    "values": ["0"],
                },
                {
                    "member": "AdvantageInvoiceLinesMart.price",
                    "operator": "equals",
                    "values": ["0"],
                },
            ],
            "measures": [
                "AdvantageInvoiceLinesMart.totalDiscount",
            ],
            "timeDimensions": [
                {
                    "dimension": "AdvantageInvoiceLinesMart.invoiceDate",
                    "granularity": "day",
                    "dateRange": "Yesterday",
                }
            ],
        },
        "payment_amounts_by_method": {
            "measures": [
                "PaymentsSummaryMart.amount",
            ],
            "timeDimensions": [
                {
                    "dimension": "PaymentsSummaryMart.invoiceDate",
                    "granularity": "day",
                    "dateRange": "Yesterday",
                }
            ],
            "order": [
                ["PaymentsSummaryMart.amount", "desc"],
                ["PaymentsSummaryMart.count", "desc"],
                ["PaymentsSummaryMart.paymentMethod", "desc"],
            ],
            "dimensions": [
                "PaymentsSummaryMart.paymentMethod",
            ],
        },
        "payments_total_amount_collected": {
            "measures": ["PaymentsSummaryMart.amount"],
            "timeDimensions": [
                {
                    "dimension": "PaymentsSummaryMart.invoiceDate",
                    "granularity": "day",
                    "dateRange": "Yesterday",
                }
            ],
            "order": [
                ["PaymentsSummaryMart.amount", "desc"],
            ],
        },
        "uploaded_documents": {
            "measures": ["PatientDocumentMart.uploads"],
            "timeDimensions": [
                {
                    "dimension": "PatientDocumentMart.createdTime",
                }
            ],
        },
        "uploaded_documents_yesterday": {
            "measures": ["PatientDocumentMart.uploads"],
            "timeDimensions": [
                {
                    "dimension": "PatientDocumentMart.createdTime",
                    "dateRange": "Yesterday",
                }
            ],
        },
        "approved_documents": {
            "measures": ["PatientDocumentMart.approved"],
            "timeDimensions": [
                {
                    "dimension": "PatientDocumentMart.createdTime",
                }
            ],
        },
        "pending_documents": {
            "measures": ["PatientDocumentMart.pending"],
            "timeDimensions": [
                {
                    "dimension": "PatientDocumentMart.createdTime",
                }
            ],
        },
        "rejected_documents": {
            "measures": ["PatientDocumentMart.rejected"],
            "timeDimensions": [
                {
                    "dimension": "PatientDocumentMart.createdTime",
                }
            ],
        },
        "total_patient_documents": {
            "measures": ["PatientSummaryMart.count"],
            "timeDimensions": [{"dimension": "PatientSummaryMart.createdDate"}],
        },
    }

    service_points = [
        queue_type.lower() for queue_type, _ in QUEUE_TYPES if queue_type != "TRIAGE"
    ]
    for service_point in service_points:
        queries[f"{service_point}_count_and_amount"] = {
            "measures": ["InvoicesMart.count", "InvoicesMart.totalPrice"],
            "timeDimensions": [
                {
                    "dimension": "InvoicesMart.invoiceDate",
                    "granularity": "day",
                    "dateRange": "Yesterday",
                }
            ],
            "filters": [
                {
                    "member": "InvoicesMart.queueType",
                    "operator": "equals",
                    "values": [service_point.title()],
                }
            ],
        }

    context: dict[Any, Any] = {}
    result: list | dict | int
    for query_name, query in queries.items():
        response = cube_js.api_call(
            url=cube_js.query_base_url, payload={"query": query}
        ).json()

        data = response["data"]
        measures: list = cast(list, query.get("measures", []))
        dimensions: list = cast(list, query.get("dimensions", []))
        fields = measures + dimensions

        if len(data) > 0:
            result = [{k: row[k] for k in fields} for row in data]  # pragma: no cover
        else:
            result = [{k: 0 for k in fields}]

        if len(fields) == 1:
            # bubble up single result
            result = next(iter(result[0].values())) or 0
        else:
            # remove mart name from field
            result = [
                {k.split(".")[-1]: (v or 0) for k, v in row.items()} for row in result
            ]

            if len(dimensions) == 0:
                # we're only doing aggregations, bubble up result
                result = result[0]

        context[query_name] = result

    # Post querying aggregations
    context["total_invoice_count"] = 0
    context["total_invoiced_amount"] = 0
    context["service_points_analysis"] = {}
    service_points_analysis = []
    for service_point in service_points:
        point = context[f"{service_point}_count_and_amount"]
        context["total_invoice_count"] += point["count"]
        context["total_invoiced_amount"] += point["totalPrice"]
        point["service_point"] = service_point.title()
        service_points_analysis.append(point)
        context.pop(f"{service_point}_count_and_amount")

    service_points_analysis = sorted(
        service_points_analysis,
        key=lambda x: (x["totalPrice"], x["count"]),
        reverse=True,
    )
    context["service_points_analysis"] = service_points_analysis

    context["total_outstanding_amount"] = max(
        context["total_invoiced_amount"] - context["payments_total_amount_collected"],
        0,
    )
    context["patients_revisits_count"] = (
        context["visits_started_count"] - context["patients_new_count"]
    )
    context["uploaded_percentage"] = (
        (context["uploaded_documents"] / context["total_patient_documents"]) * 100
        if context["total_patient_documents"] > 0
        else 0
    )

    # Wallet Balances
    wallets = get_wallet_balances(org)
    sms_balance = Decimal(wallets["bulk_sms_account"]["balance"])
    context["sms_wallet_balance"] = sms_balance
    context["sms_wallet_balance_low"] = sms_balance < 1000

    # Greeting of the day :)
    yesterday = (django_timezone.now() - timedelta(days=1)).date()
    greet_idx = xxh128(str(yesterday)).intdigest() % 5
    context["greeting"] = ["Hi", "Hello", "G'day", "Greetings", "Howdy"][greet_idx]

    # extras
    context["api_host"] = settings.API_HOST
    context["yesterday"] = yesterday
    context["currency_prefix"] = "KSh"
    bcc_emails = [
        settings.ADVANTAGE_GROUP_EMAIL,
        settings.GTM_GROUP_EMAIL,
        settings.CLIENT_SUCCESS_GROUP_EMAIL,
    ]

    subject = "SladeAdvantage Daily Digest"
    send_email(
        subject=subject,
        to=to,
        bcc=bcc_emails,
        html_temp="daily_report_email.mjml",
        plain_text="daily_report_email.mjml",
        context_obj=context,
        org_name=org.organisation_name,
        headers={"X-Entity-Ref-ID": str(uuid.uuid4())},
    )

    matrix_message = loader.get_template("daily_report_matrix.html").render(context)
    group.send_message_to_matrix_room(matrix_message)


@celery_app.task(base=BaseTaskWithRetry)
def close_service_request(service_request_id: uuid.UUID) -> None:
    """Close the service request and post accounting entries."""
    service_request = (
        ServiceRequest.objects.select_related("invoice")
        .prefetch_related("invoice__payments")
        .only("id", "invoice")
        .get(pk=service_request_id)
    )
    erp = get_erp_client(service_request.visit.workstation_id)
    invoice = service_request.invoice
    clinical_order = service_request.clinical_order

    for payment in invoice.payments.all().order_by("created"):
        erp.payment_receipts.transition(
            payment.payment_receipt_id,
            "DRAFT_SUBMIT_APPROVE",
        )
    if invoice.invoice_lines.exists():
        invoice._perform_operation_on_erp("UPDATE")
        erp.sales_invoices.transition(
            invoice.sales_invoice_id,
            "DRAFT_SUBMIT_APPROVE",
        )
        # 2 step process to make transition validation happy
        invoice._disable_sync = True
        update_state_transition(invoice, "DRAFT_SUBMIT_APPROVE")

        erp.sales_orders.transition(
            clinical_order.sales_order_id,
            "DRAFT_SUBMIT_APPROVE",
        )
        clinical_order._disable_sync = True
        update_state_transition(clinical_order, "DRAFT_SUBMIT_APPROVE")

        # get GDN(Inventory Operation) from erp and process it inorder to reduce stock
        gdn = erp.inventory_operations.get_with(
            {"source_document": clinical_order.sales_order_id}
        )
        try:
            erp.inventory_operations.auto_process_inventory(
                gdn["id"],
            )
        except Exception as exc:
            """
            `auto_process_inventory` may take a while in ERP leading to
            timeout issues or encounter errors.
            If that happens, we don't want to retry the already
            successful operations in the close_service_request scope.
            ERP will resolve the failures or any retries necessary on its end.
            """
            LOGGER.error(exc)

    else:
        erp.sales_invoices.transition(
            invoice.sales_invoice_id,
            "DRAFT_CLOSED",
        )
        update_state_transition(invoice, "DRAFT_CLOSED")

        erp.sales_orders.transition(
            clinical_order.sales_order_id,
            "DRAFT_CLOSED",
        )
        update_state_transition(clinical_order, "DRAFT_CLOSED")


@celery_app.task(base=BaseTaskWithRetry)
def complete_visit(visit_id: uuid.UUID) -> None:
    """Do 'after-visit' things."""
    visit = Visit.objects.select_related(
        "patient", "patient__person", "organisation"
    ).get(pk=visit_id)

    if visit.status != "FINISHED":
        LOGGER.warning(f"Visit {visit.id} not in FINISHED state.")
        return

    org = visit.organisation
    post_visit_survey_setting = OrganisationSetting.get_org_setting(
        org,
        "visits:post_visit_surveys_enabled",
    )
    if post_visit_survey_setting.value:
        send_post_visit_survey_sms(visit)
    else:
        LOGGER.warning(
            f"Organisation with slade code {org.slade_code} not "
            "enabled to send post visit surveys."
        )
    send_visit_summary_sms(visit)
