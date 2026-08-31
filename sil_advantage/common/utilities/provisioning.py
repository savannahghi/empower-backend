"""Provision an organisation and its first user.

Upstream an organisation arrives through Chargemaster, the Slade auth server and
the ERP: Chargemaster issues the slade code, the auth server creates the admin,
and the ERP supplies the branches and workstations that become queues. A
deployment that runs none of those still needs the same end state, so this
builds it directly:

  * the organisation, whose save() registers it as a tenant on clinical
  * a facility on clinical, and the OrgUnit that points at it
  * the screening queues
  * a Keycloak user carrying the slade code as its `business_partner` claim,
    which is how a signed-in user is mapped onto an organisation
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from sil_advantage.common.models import Organisation, OrgUnit
from sil_advantage.sil_auth.keycloak import keycloak_admin, service_account_token

LOGGER = logging.getLogger(__name__)

# ERP issues these ids upstream. Deriving them from the slade code keeps them
# stable across re-runs and distinct between organisations.
UNIT_NAMESPACE = uuid.UUID("6f2d1f6c-2f3a-4a54-9a4a-0e2b1f6c4d21")

SCREENING_QUEUES = (
    ("Breast Cancer Screening", "BREAST CANCER SCREENING"),
    ("Cervical Cancer Screening", "CERVICAL CANCER SCREENING"),
    ("Prostate Cancer Screening", "PROSTATE CANCER SCREENING"),
)


class ProvisioningError(RuntimeError):
    """Raised when an organisation cannot be provisioned."""


@dataclass
class ProvisionResult:
    """What provisioning produced, for the caller to report back."""

    organisation: Organisation
    facility_id: Optional[str] = None
    queues: list[str] = field(default_factory=list)
    created: bool = False
    user_created: bool = False


def unit_id(slade_code: int, kind: str) -> uuid.UUID:
    """Return the stable id standing in for an ERP org unit."""
    return uuid.uuid5(UNIT_NAMESPACE, f"{slade_code}:{kind}")


def next_slade_code() -> int:
    """Issue the next slade code.

    Chargemaster does this upstream; without it the highest in use plus one is
    enough to keep organisations distinct.
    """
    highest = Organisation.objects.order_by("-slade_code").first()

    return (highest.slade_code + 1) if highest else 1


def register_facility(organisation: Organisation, phone: str, address: str) -> str:
    """Create the organisation's facility on clinical and return its id."""
    headers = {
        "Authorization": f"Bearer {service_account_token()}",
        "Clinical-Organization-ID": str(organisation.tenant_id),
        "Clinical-Facility-ID": str(organisation.tenant_id),
    }
    response = requests.post(
        f"{settings.CLINICAL_SERVICE_URL}/api/v1/facilities",
        json={
            "name": f"{organisation.organisation_name} Facility",
            "phone": phone,
            "active": True,
            "country": "KE",
            "address": address,
            "description": f"{organisation.organisation_name} screening site",
            "identifier": {
                "type": "SladeCode",
                "value": str(organisation.slade_code),
            },
        },
        headers=headers,
        timeout=30,
    )

    if not response.ok:
        raise ProvisioningError(
            f"clinical rejected the facility: {response.status_code} {response.text[:200]}"
        )

    return response.json()["id"]


def ensure_queues(organisation: Organisation, actor: uuid.UUID) -> list[str]:
    """Create the screening queues the ERP workstations would have produced."""
    from sil_advantage.visits.models import Queue

    valid = {choice for choice, _ in Queue._meta.get_field("queue_type").choices}
    slade_code = organisation.slade_code
    created = []

    for name, queue_type in SCREENING_QUEUES:
        if queue_type not in valid:
            LOGGER.info("skipping %s: no %s queue type", name, queue_type)
            continue

        _, was_created = Queue.objects.get_or_create(
            name=name,
            organisation=organisation,
            defaults={
                "queue_type": queue_type,
                "cluster_id": unit_id(slade_code, "cluster"),
                "branch_id": unit_id(slade_code, "branch"),
                "department_id": unit_id(slade_code, "department"),
                "workstation_id": unit_id(slade_code, "workstation"),
                "created_by": actor,
                "updated_by": actor,
            },
        )
        if was_created:
            created.append(name)

    return created


@transaction.atomic
def provision_organisation(
    *,
    name: str,
    email: str,
    phone: str,
    first_name: str,
    last_name: str,
    slade_code: Optional[int] = None,
    password: Optional[str] = None,
    address: str = "Nairobi",
    actor: Optional[uuid.UUID] = None,
) -> ProvisionResult:
    """Create an organisation, its facility, its queues and its first user."""
    actor = actor or uuid.uuid4()
    slade_code = slade_code or next_slade_code()

    organisation, created = Organisation.objects.get_or_create(
        slade_code=slade_code,
        defaults={
            "organisation_name": name,
            "email_address": email,
            "phone_number": phone,
            "financial_year_start_date": date(date.today().year, 1, 1),
            "created_by": actor,
            "updated_by": actor,
        },
    )

    # SILUser.profile is cached with no expiry and pickles its Organisation, so
    # a stale entry would keep a user reading the wrong tenant.
    cache.clear()

    result = ProvisionResult(organisation=organisation, created=created)

    branch_id = unit_id(slade_code, "branch")
    unit = OrgUnit.objects.filter(erp_id=branch_id).first()

    if unit is None:
        facility_id = register_facility(organisation, phone, address)
        OrgUnit.objects.create(
            organisation=organisation,
            erp_id=branch_id,
            facility_id=facility_id,
            name=f"{organisation.organisation_name} Branch",
            orgunit_type="branch",
            phone_number=phone,
            created_by=actor,
            updated_by=actor,
        )
        result.facility_id = facility_id
    else:
        result.facility_id = str(unit.facility_id)

    result.queues = ensure_queues(organisation, actor)

    admin = keycloak_admin()
    admin.ensure_claim_wiring()
    result.user_created = admin.upsert_user(
        email=email,
        first_name=first_name,
        last_name=last_name,
        slade_code=slade_code,
        password=password,
    )

    return result


def provisioning_summary(result: ProvisionResult) -> dict[str, Any]:
    """Shape a result for an API response."""
    return {
        "id": str(result.organisation.id),
        "name": result.organisation.organisation_name,
        "slade_code": result.organisation.slade_code,
        "tenant_id": str(result.organisation.tenant_id),
        "facility_id": result.facility_id,
        "queues": result.queues,
        "created": result.created,
        "owner": {"email": result.organisation.email_address},
    }
