"""SMS utilities."""

import logging
import uuid
from decimal import Decimal
from math import ceil
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from sil_advantage.common.models.common_models import Person
from sil_advantage.notifications.sms import TRANSACTIONAL_SMS_INTENTIONS
from sil_advantage.notifications.sms.models import SenderID
from sil_advantage.settings.models import Organisation, OrganisationSetting

LOGGER = logging.getLogger(__name__)


def create_sms_from_template(
    intention: str,
    phone_number: str,
    organisation: Organisation,
    branch_id: uuid.UUID | None,
    person: Person,
    **kwargs: Any,
) -> dict[str, Any]:
    """Create an SMS entry in the database.

    The SMS message depends on the SMS intention, and the template
    formatted using **kwargs.
    These are then picked up by the tasks for sending.
    """
    language_preference = (
        person.language
        if person.language is not None
        else settings.MODELTRANSLATION_DEFAULT_LANGUAGE
    )

    template = OrganisationSetting.get_setting(
        organisation,
        branch_id,
        f"sms:{intention.lower()}_{language_preference}_template",
    )
    message = template.value.format(**kwargs)

    return {
        "intention": intention,
        "message": message,
        "recipients": [phone_number],
        "owner": organisation.slade_code,
    }


def get_sms_parts(sms: str) -> int:
    r"""Get number of parts an SMS has.

    Borrowed from SIL Comms.

    If an SMS only has GSM 03.38 characters, a segment is 160 characters long.
     If it has multiple segments, each is 153 characters long. The 7
     character difference contains instructions that tell the phone
     how to rebuild the message.
     The GSM charset was extended with ^{}\[~]|€ characters worth 2 chars each.
    If an SMS has at least one non GSM character, it is encoded in the UCS-2 encoding.
     UCS-2 is basically UTF-16. A segment has 70 characters each. If it has multiple
     segments, each is 67 characters each.
     Finding the length of a UCS-2 encoded SMS involves counting the number of
      UTF-16 codepoints in each character.
    Character counters to try:
        http://smscharactercount.com/#/counter
        https://twiliodeved.github.io/message-segment-calculator/
    """
    GSM_BASIC_CHARSET = (
        "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
    )
    GSM_EXT_CHARSET = "\f^{}\\[~]|€"
    GSM_CHARSET = GSM_BASIC_CHARSET + GSM_EXT_CHARSET

    is_gsm_encoded = not any(char not in GSM_CHARSET for char in sms)
    if is_gsm_encoded:
        sms_length = len(sms) + len([char for char in sms if char in GSM_EXT_CHARSET])
        segment_length = 153 if sms_length > 160 else 160
    else:
        sms_length = sum(1 if ord(char) < 65536 else 2 for char in sms)
        segment_length = 67 if sms_length > 70 else 70

    return ceil(sms_length / segment_length)


def get_branch_sender_id(
    org: Organisation,
    branch_id: uuid.UUID | None,
    intention: str,
) -> uuid.UUID | None:
    """Determine which Sender ID to use from branch settings.

    Args:
        *args: Variable positional arguments.
            - org: Intention to be used while sending the sms.
            - branch_id: Branch id belonging to an org.
            - intention: Intention to be used while sending the sms.

    Returns:
        UUID belonging to a SenderID
    """
    transactional_intentions = [
        intention[0] for intention in TRANSACTIONAL_SMS_INTENTIONS
    ]

    filters: Dict[str, Any] = {
        "organisation": org,
        "branch_id": branch_id,
    }
    if intention in transactional_intentions:
        filters["setting_name"] = "billing:transactional_sender_id"
    else:
        filters["setting_name"] = "billing:promotional_sender_id"

    setting = OrganisationSetting.get_branch_setting(**filters)
    try:
        sender = SenderID.objects.filter(name=setting.value).latest("created")
        sender_id = sender.id
        return sender_id
    except ObjectDoesNotExist:
        LOGGER.error(f"SenderID with name {setting.value} does not exist.")
        return None


def get_pricing_rate(customer_id: Optional[uuid.UUID], intention: str) -> Decimal:
    """Fetch the pricing rate for an organization."""
    from sil_advantage.common.api_clients.erp import fetch_from_erp_cache

    sil_org = fetch_from_erp_cache(
        "organisations",
        "get_with",
        filter={
            "slade_code": settings.TRANSACTING_SIL_ORG_SLADE_CODE,
        },
    )
    filters = {
        "organisation": sil_org["id"],
        "billing_code": f"{intention}_SMS",
    }
    # Get customer specific pricing if available
    if customer_id:
        pricing = fetch_from_erp_cache(
            "pricing_table_lines", "list", filters={**filters, "customer": customer_id}
        )
    else:
        pricing = {"results": []}
    if not pricing["results"]:
        # Fall back to sil org pricing
        filters["customer"] = None
        pricing = fetch_from_erp_cache(
            "pricing_table_lines",
            "list",
            filters=filters,
        )
        if not pricing["results"]:
            raise ValueError("No pricing information found")
    return (
        Decimal(pricing["results"][0]["rate"])
        if len(pricing["results"]) > 0
        else Decimal(1.0)
    )


def can_send_sms(
    org: Organisation,
    branch_id: uuid.UUID | None,
    intention: str,
    message: str,
    n_recipients: int,
) -> tuple[bool, Optional[str], int, Optional[Decimal], dict]:
    """Check if this organisation can send an SMS and return pricing information."""
    from sil_advantage.billing.utils import get_wallet_balances

    wallets = get_wallet_balances(org, branch_id)
    wallet = wallets.get("bulk_sms_account", None)
    n_parts = get_sms_parts(message)

    try:
        rate = get_pricing_rate(org.customer_id, intention)

    except Exception as e:
        msg = f"Error fetching pricing information: {str(e)}"
        return False, msg, n_parts, None, wallets

    estimated_cost = rate * n_parts * n_recipients

    if wallet is None or wallet["balance"] <= estimated_cost:
        msg = "Bulk SMS wallet doesn't have enough balance"
        return False, msg, n_parts, estimated_cost, wallets

    return True, None, n_parts, estimated_cost, wallets


def send_custom_sms(
    sms_intention: str,
    phone_number: str,
    org: Organisation,
    branch_id: uuid.UUID | None,
    person: Person,
    priority: int,
    **kwargs: Any,
) -> None:
    """This is a resusable function to send sms to patients and practitioners."""
    from sil_advantage.notifications.sms.tasks import send_sms

    sender_id: uuid.UUID | None = None

    if branch_id:
        sender_id = get_branch_sender_id(org, branch_id, sms_intention)

    has_consent_for_sms = person.person_contacts.filter(
        contact_type="phone_number", consent_to_contact_given=True
    ).exists()
    if phone_number and has_consent_for_sms:
        sms = create_sms_from_template(
            sms_intention,
            phone_number,
            org,
            branch_id,
            person,
            fname=person.first_name,
            provider_name=org.organisation_name,
            **kwargs,
        )
        send_sms.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=priority,
            args=(
                sms["intention"],
                sms["message"],
                sms["recipients"],
                sms["owner"],
                branch_id,
                kwargs.get("workstation_id"),
            ),
            kwargs={"sender_id": sender_id},
        )
