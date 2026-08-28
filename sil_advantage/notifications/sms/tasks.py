"""SMS tasks."""
import logging
import uuid
from io import BytesIO
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.utils import timezone
from openpyxl import Workbook
from sil_comms_client import SILComms

from sil_advantage.common.models import Organisation
from sil_advantage.common.models.common_models import Attachment
from sil_advantage.common.tasks import BaseTaskWithRetry
from sil_advantage.config import celery_app
from sil_advantage.notifications.sms import TRANSACTIONAL_SMS_INTENTIONS
from sil_advantage.notifications.sms.models import (
    SMS,
    ProcessState,
    SenderID,
    SMSLogReport,
)
from sil_advantage.notifications.sms.utils import can_send_sms
from sil_advantage.sil_auth.models import SILUser

LOGGER = logging.getLogger(__file__)


@celery_app.task(base=BaseTaskWithRetry)
def send_sms(
    intention: str,
    message: str,
    recipients: list[str],
    owner: int,  # slade code
    branch_id: uuid.UUID,
    workstation_id: uuid.UUID,
    sender_id: uuid.UUID | None = None,
    model_name: str | None = None,
    model_obj_pk: uuid.UUID | None = None,
) -> None:
    """Push SMS to the SIL Comms gateway.

    Args:
        *args: Variable positional arguments.
            - intention: Intention to be used while sending the sms.
            - message: Body of text to be received by recipients.
            - recipients: List of contacts to receive the sms.
            - owner: slade code belonging to an org.
            - branch_id: branch id belonging to an org.
            - workstation_id: workstation id belonging to an org.

        **kwargs: Variable keyword arguments.
            - sender_id: Unique ID of a SenderID instance.
            - model_name: Name of the model tracking an sms.
            - model_obj_pk: Unique ID of a model instance tracking an sms.

    Returns:
        None
    """
    # imports are here due to circular dependency issues
    from sil_advantage.billing.tasks import send_billing_event_to_erp
    from sil_advantage.billing.utils import get_wallet_balances

    env = settings.ENVIRONMENT.lower()
    is_test = env == "test"
    org = Organisation.objects.get(slade_code=owner)

    can_send, err, n_parts, estimated_cost, wallets = can_send_sms(
        org,
        branch_id,
        intention,
        message,
        len(recipients),
    )
    if not can_send:
        LOGGER.error(err)
        return
    sms_client = SILComms(**settings.SIL_COMMS_API_CONFIG)
    transactional_intentions = [
        intention[0] for intention in TRANSACTIONAL_SMS_INTENTIONS
    ]

    if sender_id is None:
        if intention in transactional_intentions:
            sender = settings.SIL_COMMS_TRANSACTIONAL_SENDER_ID
            service = "TRANSACTIONAL_BULK_SMS"
        else:
            sender = settings.SIL_COMMS_PROMOTIONAL_SENDER_ID
            service = "PROMOTIONAL_BULK_SMS"
        sender_obj = SenderID.objects.filter(name=sender).latest("created")
    else:
        sender_obj = SenderID.objects.get(id=sender_id)
        sender = sender_obj.name
        service = sender_obj.service

    # For non prod environments only send to whitelisted numbers only and add
    # "Test Message" suffix
    if is_test:
        message += " [Test Message]"
        whitelisted_recipients = settings.WHITELISTED_TEST_RECIPIENTS
        # Only send to whitelisted numbers
        recipients = list(set(recipients).intersection(whitelisted_recipients))

    # In the case that there are not recipients just exit
    if not recipients:
        # If there are no recipients exit the process here
        LOGGER.warning("No recipients to send the message to")
        return

    payload = {
        "sender": sender,
        "message": message,
        "app": settings.SIL_COMMS_BUSINESS_PARTNER_APP_ID,
        "recipients": recipients,
        "metadata": {
            "intention": intention,
            "owner": owner,
            "source": env,
            "service": "SLADE360_ADVANTAGE",
        },
    }
    response = sms_client.bulksms.create(payload=payload)

    send_billing_event_to_erp.apply_async(
        queue=settings.CELERY_DEFAULT_QUEUE,
        priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
        args=(
            service,
            f"{intention}_SMS",
            n_parts * len(recipients),
            "bulk_sms_account",
            response["guid"],
            str(timezone.now()),
            workstation_id,
            org.customer_id,
            branch_id,
        ),
    )

    admin_email = settings.SYSTEM_ADMIN_EMAIL
    system_admin = SILUser.objects.get(email=admin_email).id

    sms = SMS.objects.create(
        organisation=org,
        branch_id=branch_id,
        sender=sender_obj,
        message=message,
        recipients=recipients,
        intention=intention,
        sil_comms_sms_id=response["sms"][0],
        created_by=system_admin,
        updated_by=system_admin,
    )

    if model_name and model_obj_pk:
        Model = apps.get_model(model_name)
        try:
            instance = Model.objects.get(pk=model_obj_pk)
            instance.sms = sms
            instance.save()
        except Model.DoesNotExist:
            LOGGER.error(
                f"Object with ID {model_obj_pk} of type {model_name} does not exist."
            )

    # invalidate the cache
    wallets = get_wallet_balances(org, branch_id)
    cache.delete(wallets["_cache_key"])


@celery_app.task()
def process_delivery_report(payload: dict[str, Any]) -> None:
    """Process an SMS delivery report from SIL Comms.

    Payload format:
        {
            "status" : "<str>", # success or error
            "message" : "<str>",
            "type" : "DELIVERY_REPORT",
            "data" : {
                "guid" : "<guid>",
                "body" : "<str>",
                "msisdn" : "<254KXXYYYZZZ>",
                "sms_type" : "<str>",
                "gateway" : "<str>",
                "carrier": "<str>",
                "subscription" : <str>,
                "direction" : "<str>",
                "state" : "<str>",
                "created": "<YYYY-MM-DD HH:mm:SS>",
                "updated": "<YYYY-MM-DD HH:mm:SS>"
        }

    Args:
        payload: SMS delivery report payload received from SIL Comms.
    """
    sms_data = payload["data"]
    sil_comms_sms_id = sms_data["guid"]

    try:
        sms = SMS.objects.get(sil_comms_sms_id=sil_comms_sms_id)
    except ObjectDoesNotExist:
        LOGGER.warning(
            f"SMS object with sil_comms_id {sil_comms_sms_id} does not exist."
        )
        return

    if payload["status"] == "error":
        sms.failure_reason = payload["message"]
    sms.state = sms_data["state"]
    sms.save()


@celery_app.task()
def process_interactive_shortcode(payload: dict[str, Any]) -> None:
    """Process an interactive shortcode SMS response from SIL Comms.

    Payload format:
        {
            "Msisdn" : "<254KXXYYYZZZ>",
            "Shortcode" : "<shortcode>",
            "Response" : "<str>"
        }

    Args:
        payload: SMS response payload received from SIL Comms.
    """
    msisdn = payload.get("Msisdn")
    shortcode = payload.get("Shortcode")
    response_message = payload.get("Response", "No message provided")

    try:
        last_message = SMS.objects.filter(
            sender__name=shortcode,
            recipients__contains=[msisdn],
            delivery_type="OUTBOUND",
        ).latest("created")
    except SMS.DoesNotExist:
        LOGGER.warning(
            f"Latest SMS sent using Shortcode {shortcode} to {msisdn} not found."
        )
        return

    admin_email = settings.SYSTEM_ADMIN_EMAIL
    system_admin = SILUser.objects.get(email=admin_email).id
    intention = "DIRECT_MESSAGE"

    SMS.objects.create(
        sender=last_message.sender,
        message=response_message,
        recipients=[msisdn],
        delivery_type="INBOUND",
        state="RECEIVED",
        created_by=system_admin,
        updated_by=system_admin,
        intention=intention,
        cluster_id=last_message.sender.cluster_id,  # type: ignore
        branch_id=last_message.sender.branch_id,  # type: ignore
        organisation=last_message.organisation,
    )

    LOGGER.info("SMS successfully processed.")


@celery_app.task()
def generate_sms_log_report(payload: dict[str, Any], sms_report_id: uuid.UUID) -> None:
    """Generates an SMS report."""
    delivery_type = payload.get("delivery_type", None)
    date_from = payload["date_from"]
    date_to = payload["date_to"]

    sms_report = SMSLogReport.objects.get(id=sms_report_id)

    common_fields = {
        "organisation": sms_report.organisation,
        "created_by": sms_report.created_by,
        "updated_by": sms_report.updated_by,
        "workstation_id": sms_report.workstation_id,
        "department_id": sms_report.department_id,
        "cluster_id": sms_report.cluster_id,
        "branch_id": sms_report.branch_id,
    }

    sms_qs = SMS.objects.filter(
        organisation=sms_report.organisation,
        branch_id=sms_report.branch_id,
        created__date__gte=date_from,
        created__date__lte=date_to,
    ).select_related()

    if not sms_qs:
        sms_report.process_state = ProcessState.FAILED
        sms_report.failure_reason = "No SMS's found within the give period."
        sms_report.save()
        return

    if delivery_type:
        sms_qs = sms_qs.filter(delivery_type=delivery_type)
    else:
        delivery_type = "ALL"

    work_book = Workbook()
    work_sheet = work_book.active
    work_sheet.title = "Message Log Report"
    headers = [
        "Delivery Type",
        "Message",
        "Sent On",
        "From",
        "To",
        "Status",
    ]
    work_sheet.append(headers)

    for sms in sms_qs.iterator():
        sms_list = []
        sms_list.append(sms.delivery_type)
        sms_list.append(sms.message)
        sms_list.append(
            sms.created.strftime("%A %d. %B %Y")  # type: ignore  # noqa: B950
        )
        sms_list.append(sms.from_name)  # type: ignore
        sms_list.append(sms.to)  # type: ignore
        sms_list.append(sms.state)  # type: ignore

        work_sheet.append(sms_list)

    file_name = f"Log-{delivery_type}-{date_from}-{date_to}.xlsx"

    report_file = BytesIO()
    work_book.save(report_file)
    report_file.seek(0)

    report_content = ContentFile(report_file.getvalue(), name=file_name)

    attachment = Attachment(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=report_content,
        title=file_name,
        size=report_content.size,
        **common_fields,
    )
    attachment.save()

    sms_report.report_file = attachment
    sms_report.process_state = ProcessState.COMPLETE
    sms_report.save()
