"""Organisation related models."""
import logging
import uuid
from typing import Any, Optional, Self

import requests
from django.conf import settings
from django.db import models, transaction
from django.db.models import JSONField
from django.utils.functional import cached_property
from phonenumber_field.modelfields import PhoneNumberField
from sil_erp_client import ERP
from sil_transitions.mixins import TransitionAndLogMixin
from sil_wrapper_utils.exceptions import ItemNotFound

from sil_advantage.common.constants import (
    COUNTRY_CODES,
    ONBOARDING_SESSION_LEVEL_STATUSES,
    ORGANISATION_ONBOARDING_PREFERENCES,
    ORGANIZATION_ONBOARDING_STATUSES,
)
from sil_advantage.common.models.mixins import OrgUnitIdsMixin

LOGGER = logging.getLogger(__file__)

ORG_TRANSITION_GRAPH = {True: [False], False: [True]}

WORKSTATION_QUEUE_MAPPING = {
    "cashier": "BILLING",
    "pharmacy_dispensing": "PHARMACY",
    "triage": "TRIAGE",
    "lab": "LAB",
    "imaging": "IMAGING",
    "procedure": "PROCEDURE",
    "optical": "OPTICAL",
    "breast_cancer_screening": "BREAST CANCER SCREENING",
    "cervical_cancer_screening": "CERVICAL CANCER SCREENING",
}


class OrganisationAbstractBase(models.Model):
    """Base class for Organisation."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    created_by = models.UUIDField(editable=False)
    updated_by = models.UUIDField()

    class Meta:
        """Define a sensible default ordering for organisations."""

        ordering = ("-updated", "-created")
        abstract = True


class OrganisationTransitionLog(OrganisationAbstractBase):
    """Record every time an org changes between active and inactive."""

    active_from = models.CharField(max_length=255)
    active_to = models.CharField(max_length=255)
    organisation = models.ForeignKey(
        "Organisation",
        related_name="organisation_logs",
        on_delete=models.PROTECT,
    )
    note = models.TextField()

    def __str__(self) -> str:
        """Render note as a string representation."""
        return self.note


class Organisation(  # type: ignore[django-manager-missing]
    TransitionAndLogMixin,
    OrganisationAbstractBase,
):
    """Define organisations - the main unit of partitioning.

    Very thin. Org, financial year & currency setup should be done on the ERP.
    """

    _transition_field = "active"
    _transition_log_model_fk_field = "organisation"
    _transition_log_model = OrganisationTransitionLog
    _transition_graph = ORG_TRANSITION_GRAPH

    slade_code = models.IntegerField(unique=True)
    active = models.BooleanField(default=True)
    deleted = models.BooleanField(default=False)
    organisation_name = models.CharField(max_length=100, unique=True)

    email_address = models.EmailField(max_length=100)
    phone_number = PhoneNumberField()
    description = models.TextField(null=True, blank=True)
    postal_address = models.CharField(max_length=100, blank=True)
    physical_address = models.TextField(blank=True)
    default_country = models.CharField(
        max_length=255,
        choices=COUNTRY_CODES,
        default="KEN",
    )

    financial_year_start_date = models.DateField()

    # Clinical Service
    tenant_id = models.UUIDField(unique=True, null=True)

    # ERP
    customer_id = models.UUIDField(unique=True, null=True)

    def __str__(self) -> str:
        """Represent an organisation using it's name."""
        return self.organisation_name

    def natural_key(self) -> int:
        """Emit a natural key when serializing data."""
        return self.slade_code

    def transition(self, data: dict) -> None:
        """Allow ``notes`` to be added to the `OrganisationTransitionLog`."""
        self.note = data["note"]
        super().transition(data)

    def transition_log_data(self) -> dict:
        """Prepare a transition log data dict that is ready to be saved."""
        data = super().transition_log_data()
        data.update(
            {
                "created_by": self.updated_by,
                "updated_by": self.updated_by,
            }
        )
        return data

    @cached_property
    def short_name(self) -> str:
        """Get a short name version of the org's name."""
        max_length = 20
        length = 0
        name = self.organisation_name.split()
        result = []
        for word in name:
            word = word.strip()
            length += len(word)
            if length > max_length:
                break
            result.append(word)
        return " ".join(result)

    @cached_property
    def _erp_client(self) -> ERP:
        """Return the ERP client."""
        # import's here due to circular dependency issues
        from sil_advantage.common.api_clients import get_erp_client

        return get_erp_client(None)

    def create_on_erp(self) -> None:
        """Create an organisation on the ERP."""
        if not settings.SYNC_WITH_ERP:  # type: ignore  # import cycle issue
            return

        erp = self._erp_client
        # Ensure that organisation IDs on Advantage Backend
        # match those in the ERP
        try:
            erp_org = erp.organisations.get_with(
                {"slade_code": self.slade_code},
            )
        except ItemNotFound:
            financial_year = self.financial_year_start_date.strftime("%Y-%m-%d")
            erp_org = erp.organisations.setup_organisation(
                {
                    "slade_code": self.slade_code,
                    "organisation_name": self.organisation_name,
                    "email_address": self.email_address,
                    "phone_number": str(self.phone_number),
                    "description": self.description,
                    "postal_address": self.postal_address,
                    "physical_address": self.physical_address,
                    "default_country": self.default_country,
                    "financial_year_start_date": financial_year,
                    "client_types": [
                        {"name": "Healthcare Provider", "code": "PROVIDER"}
                    ],
                }
            )
        self.id = erp_org["id"]

    def create_tenant_on_clinical_server(self) -> None:
        """Create a tenant on the clinical server."""
        # import's here due to circular dependency issues
        from sil_advantage.common.api_clients import get_auth_server_credentials

        sync = settings.SYNC_WITH_CLINICAL_SERVICE  # type: ignore
        if self.tenant_id is not None or not sync:
            return

        credz = get_auth_server_credentials()

        payload = {
            "name": self.organisation_name,
            "phoneNumber": str(self.phone_number),
            "identifiers": [
                {
                    "type": "SladeCode",
                    "value": str(self.slade_code),
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {credz['access_token']}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            f"{settings.CLINICAL_SERVICE_URL}/api/v1/tenants",  # type: ignore
            json=payload,
            headers=headers,
        ).json()
        self.tenant_id = response["id"]

        if not self._state.adding:
            self.save(update_fields=["tenant_id"])

    def create_facilities_on_clinical_server(self) -> None:
        """Create facilities on the clinical server."""
        # import's here due to circular dependency issues
        from sil_advantage.common.api_clients import get_auth_server_credentials

        if not settings.SYNC_WITH_CLINICAL_SERVICE:  # type: ignore
            return

        credz = get_auth_server_credentials()

        erp = self._erp_client
        erp_branches = erp.org_units.list(
            filters={
                "orgunit_type": "branch",
                "organisation": str(self.id),
            }
        )["results"]

        existing = set(
            [
                str(unit.erp_id)
                for unit in OrgUnit.objects.filter(organisation=self).only(
                    "id", "erp_id"
                )
            ]
        )
        for erp_branch in erp_branches:
            if erp_branch["id"] in existing:
                continue

            payload = {
                "name": erp_branch["name"],
                "phoneNumber": erp_branch["phone_number"],
                "identifiers": [
                    {
                        "type": "SladeCode",
                        "value": str(self.slade_code),
                    }
                ],
            }
            headers = {
                "Authorization": f"Bearer {credz['access_token']}",
                "Content-Type": "application/json",
            }
            response = requests.post(
                f"{settings.CLINICAL_SERVICE_URL}/api/v1/facilities",  # type: ignore
                json=payload,
                headers=headers,
            ).json()

            unit = OrgUnit(
                facility_id=response["id"],
                erp_id=erp_branch["id"],
                name=erp_branch["name"],
                organisation=self,
                orgunit_type=erp_branch["orgunit_type"],
                phone_number=erp_branch["phone_number"],
                created_by=self.updated_by,
                updated_by=self.updated_by,
            )
            unit.save()

    def create_queues_for_workstations(self) -> None:
        """Create queues for workstations."""
        # import's here due to circular dependency issues
        from sil_advantage.visits.models import QUEUE_TYPES, Queue

        if not settings.SYNC_WITH_ERP:  # type: ignore
            return

        erp = self._erp_client
        workstations = erp.workstations.list(
            filters={
                "organisation": str(self.id),
            }
        )["results"]

        for workstation in workstations:
            queue_type = WORKSTATION_QUEUE_MAPPING.get(
                workstation.get("workstation_type"),
                None,
            )
            if queue_type is None:
                continue

            queue_types = {queue[0]: queue[1] for queue in QUEUE_TYPES}
            queue_name = queue_types[queue_type]
            # Done this way to "upsert" existing records
            # that don't have org. unit IDs, self-healing :)
            Queue.objects.update_or_create(
                name=queue_name,
                queue_type=queue_type,
                organisation=self,
                defaults={
                    "branch_id": workstation["branch_id"],
                    "department_id": workstation["org_unit"],
                    "workstation_id": workstation["id"],
                    "created_by": self.updated_by,
                    "updated_by": self.updated_by,
                },
            )

    def create_customer_on_erp(self) -> None:
        """Create this organisation as a SIL customer on the ERP."""
        # import's here due to circular dependency issues
        from sil_advantage.common.api_clients.erp import fetch_from_erp_cache

        sync = settings.SYNC_WITH_ERP  # type: ignore
        if self.customer_id is not None or not sync:
            return

        erp = self._erp_client
        sil_org = fetch_from_erp_cache(
            "organisations",
            "get_with",
            filter={
                "slade_code": settings.TRANSACTING_SIL_ORG_SLADE_CODE,
            },
        )

        try:
            # Check if they already exist
            # Possibly registered by another service like SIL Comms
            customer = erp.customers.get_with(
                filter={
                    "organisation": sil_org["id"],
                    "slade_code": self.slade_code,
                }
            )
        except ItemNotFound:
            currency_result = fetch_from_erp_cache(
                "currencies",
                "list",
                filters={
                    "organisation": sil_org["id"],
                    "is_default": True,
                },
            )["results"]
            if not currency_result:
                LOGGER.error(
                    f"Error: Default currency not found while "
                    f"creating {self.organisation_name}",
                    exc_info=True,
                    extra={
                        "organization_name": self.organisation_name,
                    },
                )
                raise ValueError("Invalid Currency: Default currency not found.")
            else:
                currency = currency_result[0]

            customer = erp.customers.create(
                {
                    "partner_name": self.organisation_name,
                    "is_customer": True,
                    "organisation": sil_org["id"],
                    "customer_type": "PROVIDER",
                    "country": self.default_country,
                    "currency": currency["id"],
                    "created_by": self.updated_by,
                    "updated_by": self.updated_by,
                    "slade_code": self.slade_code,
                }
            )
        self.customer_id = customer["id"]

        if not self._state.adding:
            self.save(update_fields=["customer_id"])

    def create_onboarding_flow(self) -> None:
        """Create the onboarding flow of an organisation."""
        provider_onboarding_preferences = {
            "questions": ORGANISATION_ONBOARDING_PREFERENCES
        }
        org_data = {
            "organisation": self,
            "preferences": provider_onboarding_preferences,
            "updated_by": self.updated_by,
            "created_by": self.created_by,
        }
        OrganisationOnboarding.objects.create(**org_data),

    def create_on_provider_is(self) -> None:
        """Create the organisation on the provider information system."""
        from sil_advantage.common.api_clients.is_client import get_is_client

        if not settings.SYNC_WITH_PROVIDER_IS:  # type: ignore
            return

        is_client = get_is_client()
        is_client.business_partners.create_site_settings(slade_code=self.slade_code)
        return None

    @transaction.atomic
    def save(self, *args: Any, **kwargs: Any) -> Optional[Self]:
        """Ensure that a newly created organisation gets system data."""
        obj_exists = self.__class__.objects.filter(pk=self.pk)

        if not obj_exists:
            self.create_on_erp()
            self.create_on_provider_is()
            self.create_tenant_on_clinical_server()
            self.create_customer_on_erp()
            self.create_onboarding_flow()
        else:
            self.financial_year_start_date = obj_exists[0].financial_year_start_date

        super().save(*args, **kwargs)

        if obj_exists:
            return self

        self.create_facilities_on_clinical_server()
        self.create_queues_for_workstations()

        return None


class OrgUnit(OrganisationAbstractBase):
    """Light wrapper around ERP Organisation Units."""

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.PROTECT,
        related_name="org_units",
    )

    # Clinical Service
    facility_id = models.UUIDField(unique=True)

    # ERP
    erp_id = models.UUIDField(unique=True)
    name = models.CharField(max_length=100)
    orgunit_type = models.CharField(
        choices=(("cluster", "Cluster"), ("branch", "Branch"), ("dept", "Department")),
        max_length=255,
    )
    phone_number = PhoneNumberField()


class OrganisationOnboardingTransitionLog(OrganisationAbstractBase):
    """Record every time the verification status of an org changes.

    Hold organisation verification status state transition logs.
    """

    verification_status = models.ForeignKey(
        "OrganisationOnboarding",
        on_delete=models.PROTECT,
        related_name="state_transition_logs",
    )
    status = models.CharField(
        max_length=20, choices=ORGANIZATION_ONBOARDING_STATUSES.CHOICES
    )
    status_from = models.CharField(
        max_length=20, choices=ORGANIZATION_ONBOARDING_STATUSES.CHOICES
    )
    status_to = models.CharField(
        max_length=20, choices=ORGANIZATION_ONBOARDING_STATUSES.CHOICES
    )


class OrganisationOnboarding(
    OrganisationAbstractBase, TransitionAndLogMixin, OrgUnitIdsMixin
):
    """Organization onboarding details."""

    organisation = models.OneToOneField(
        Organisation, on_delete=models.PROTECT, related_name="onboarding"
    )
    verification_status = models.CharField(
        max_length=255,
        choices=ORGANIZATION_ONBOARDING_STATUSES.CHOICES,
        default=ORGANIZATION_ONBOARDING_STATUSES.PENDING,
    )
    onboarding_session_level = models.CharField(
        max_length=255,
        choices=ONBOARDING_SESSION_LEVEL_STATUSES.CHOICES,
        default=ONBOARDING_SESSION_LEVEL_STATUSES.INTERESTS,
    )
    preferences = JSONField(default=dict)

    _transition_field = "verification_status"
    _transition_log_model_fk_field = "verification_status"
    _transition_log_model = OrganisationOnboardingTransitionLog
    _transition_graph = (
        ORGANIZATION_ONBOARDING_STATUSES.ONBOARDING_STATUS_TRANSITION_GRAPH
    )
