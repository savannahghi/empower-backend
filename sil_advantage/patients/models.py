"""Patient models."""
import logging
from dataclasses import asdict
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from sil_cacheable.orm import CacheableManager

from sil_advantage.common.models import (
    AbstractAttachment,
    AbstractBase,
    OrgUnitIdsMixin,
    Person,
    TransitionValidationMixin,
)
from sil_advantage.common.models.common_models import Attachment
from sil_advantage.integrations.mixins import RemoteObjectMixin
from sil_advantage.patients.tasks import send_patient_registration_sms
from sil_advantage.settings.models import OrganisationSetting

PATIENT_DOCUMENT_TYPES = (
    ("CLINICAL_NOTES", "CLINICAL_NOTES"),
    ("DISCHARGE_SUMMARY", "DISCHARGE_SUMMARY"),
    ("FINAL_BILL", "FINAL_BILL"),
    ("INTERIM_BILL", "INTERIM_BILL"),
    ("LAB_RESULTS", "LAB_RESULTS"),
    ("MEDICAL_REPORT", "MEDICAL_REPORT"),
    ("PRE_AUTHORIZATION_FORM", "PRE_AUTHORIZATION_FORM"),
    ("PRESCRIPTION", "PRESCRIPTION"),
    ("PROCEDURE_RESULTS", "PROCEDURE_RESULTS"),
    ("RADIOLOGY_RESULTS", "RADIOLOGY_RESULTS"),
    ("OTHER", "OTHER"),
)

PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
ARCHIVED = "ARCHIVED"

REVIEW_STATES = (
    (PENDING, "PENDING"),
    (APPROVED, "APPROVED"),
    (REJECTED, "REJECTED"),
    (ARCHIVED, "ARCHIVED"),
)

PROCESSING_STATES = (
    ("PENDING", "PENDING"),
    ("IN_PROGRESS", "IN_PROGRESS"),
    ("COMPLETE", "COMPLETE"),
    ("FAILED", "FAILED"),
)

DOCUMENT_STATUS_TRANSITION_GRAPH = {
    "PENDING": ["APPROVED", "REJECTED"],
    "APPROVED": [],
    "REJECTED": ["ARCHIVED"],
    "ARCHIVED": [],
}

UPLOAD_TYPES = (
    ("SEGMENT", "SEGMENT"),
    ("GENERAL", "GENERAL"),
)

REGISTRATION_SOURCE = (
    ("ADVANTAGE_USER_REGISTRATION", "ADVANTAGE_USER_REGISTRATION"),
    ("UPLOAD", "UPLOAD"),
    ("USSD_SELF_ENROLLMENT", "USSD_SELF_ENROLLMENT"),
)

SYNC_STATUS = (
    ("PENDING", "PENDING"),
    ("SUCCESS", "SUCCESS"),
    ("FAILED", "FAILED"),
)
LOGGER = logging.getLogger(__file__)


class Patient(  # type: ignore
    RemoteObjectMixin,
    OrgUnitIdsMixin,
    AbstractBase,
):
    """Patient details."""

    person = models.OneToOneField(
        Person,
        on_delete=models.PROTECT,
        related_name="patient_person",
    )
    file_number = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    # ERP
    customer_id = models.UUIDField(null=True, blank=True)
    # Health CRM
    global_health_id = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        db_index=True,
        help_text="""The patient's global identifier issued by health CRM.""",
    )
    health_crm_sync_status = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        choices=SYNC_STATUS,
        help_text="Indicates the sync status of the patient with Health CRM.",
    )
    # Clinical Service
    clinical_id = models.UUIDField(null=True, blank=True)

    # patient registration attribution
    source = models.CharField(
        null=True,
        blank=True,
        choices=REGISTRATION_SOURCE,
        max_length=50,
        default="ADVANTAGE_USER_REGISTRATION",
    )

    expected_delivery_date = models.DateField(null=True, blank=True)

    _remote_obj_refs = {
        "ERP": [
            (
                "customers",
                {
                    "customer_id": "id",
                },
            ),
        ],
        "CLINICAL_SERVICE": [
            (
                "patient",
                {
                    "clinical_id": "id",
                },
            )
        ],
        "HEALTH_CRM": [
            (
                "profiles",
                {},
            )
        ],
    }

    objects: models.Manager["Patient"] = CacheableManager()
    _related_serialized_models = (
        "common_person",
        "common_personcontact",
        "common_personid",
    )

    class Meta(AbstractBase.Meta):
        """Set Model options."""

        unique_together = [
            (
                "file_number",
                "organisation",
            ),
        ]

    @cached_property
    def patient_id(self) -> str:
        """Generate a human readable version of `file_number`.

        Customizable across providers e.g. MRZ-055/22, ORE-89
        """
        setting = OrganisationSetting.get_org_setting(
            self.organisation_id, "patients:patient_id_format"
        )
        return setting.value.format(
            file_number=self.file_number,
            created=self.created,
        )

    def __str__(self) -> str:
        """Represent the patient using their provider specific patient_id."""
        return "Patient ID: {}".format(self.patient_id)

    @property
    def erp_customers_payload(self) -> dict:
        """Generate the payload to create/update them on the ERP."""
        # imports are here due to circular dependency issues
        # when Django is setting up apps
        from sil_advantage.common.api_clients.erp import fetch_from_erp_cache

        payload = {
            "partner_name": self.person.get_full_name(),
            "is_customer": True,
            "organisation": str(self.organisation_id),
            "customer_type": "PATIENT",
            "country": self.organisation.default_country.split(":")[0],
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }

        if self._state.adding or self.customer_id is None:
            currencies = fetch_from_erp_cache(
                "currencies",
                "list",
                filters={
                    "organisation": str(self.organisation_id),
                    "is_default": True,
                },
            )
            payload["currency"] = currencies["results"][0]["id"]

        return payload

    @property
    def health_crm_profiles_payload(self) -> dict:
        """Generate a profiles payload to use on Health CRM."""
        person = (
            Person.objects
            .select_related("organisation")
            .prefetch_related("person_ids", "person_contacts")
            .get(id=self.person_id)
        )  # fmt: skip
        payload: dict = {
            "profile_id": str(self.pk),
            "first_name": person.first_name,
            "last_name": person.last_name,
            "other_name": person.other_names or "",
            "gender": person.gender,
            "date_of_birth": person.date_of_birth,
            "slade_code": person.organisation.slade_code,
            "service_code": settings.HEALTH_CRM_SERVICE_CODE,
            "enrolment_date": self.created.date(),
        }

        identifiers = [
            {
                "identifier_type": "PATIENT_NO",
                "identifier_value": str(self.file_number),
                "verified": True,
            }
        ]
        id_mapping = {
            "nationalID": "NATIONAL_ID",
            "passportID": "PASSPORT_NO",
            "militaryID": "MILITARY_ID",
            "alienID": "ALIEN_ID",
        }
        for person_id in person.person_ids.all().iterator():
            identifiers.append(
                {
                    "identifier_type": id_mapping[person_id.id_document_type],
                    "identifier_value": person_id.id_value,
                }
            )
        if self.customer_id is not None:
            identifiers.append(
                {
                    "identifier_type": "ERP_CUSTOMER_ID",
                    "identifier_value": str(self.customer_id),
                    "verified": True,
                }
            )
        if self.clinical_id is not None:
            identifiers.append(
                {
                    "identifier_type": "FHIR_PATIENT_ID",
                    "identifier_value": str(self.clinical_id),
                    "verified": True,
                }
            )
        payload["identifiers"] = identifiers

        contacts = []
        for contact in person.person_contacts.all().iterator():
            contacts.append(
                {
                    "contact_type": contact.contact_type.upper(),
                    "contact_value": contact.contact,
                    "verified": contact.verified,
                    "consent_to_contact_given": contact.consent_to_contact_given,
                }
            )
        payload["contacts"] = contacts

        return payload

    @property
    def clinical_service_patient_payload(self) -> dict:
        """Generate a payload to create a patient on the clinical service."""
        person = (
            Person.objects
            .prefetch_related("person_ids")
            .get(id=self.person_id)
        )  # fmt: skip

        payload: dict = {
            "input": {
                "firstName": person.first_name,
                "lastName": person.last_name,
                "otherNames": person.other_names or "",
                "birthDate": str(person.date_of_birth)
                if person.date_of_birth
                else "1900-01-01",
                "gender": person.gender.lower() if person.gender else "OTHER",
            }
        }

        identifiers = []
        # Values are clinical's IdentifierType enum, which is lower case.
        id_mapping = {
            "nationalID": "national_id",
            "passportID": "passport_number",
            "alienID": "alien_id",
        }
        for person_id in person.person_ids.all().iterator():
            try:
                identifiers.append(
                    {
                        "type": id_mapping[person_id.id_document_type],
                        "value": person_id.id_value,
                    }
                )
            except KeyError:
                LOGGER.warning(
                    f"ID Mapping with key {person_id.id_document_type} does not exist."
                )

        # Only sent once assigned; clinical rejects an empty identifier value.
        if self.global_health_id:
            identifiers.append(
                {
                    "type": "slade_health_id",
                    "value": self.global_health_id,
                }
            )

        payload["input"]["identifiers"] = identifiers

        contacts = []
        for contact in person.person_contacts.filter(contact_type="phone_number"):
            contacts.append(
                {
                    "type": "PHONE_NUMBER",
                    "value": contact.contact,
                }
            )
        payload["input"]["contacts"] = contacts

        return payload

    def _generate_file_number(self) -> None:
        """Generate a file number for a patient."""
        patient = (
            Patient.objects.filter(organisation=self.organisation_id)
            .order_by("-file_number")
            .first()
        )
        if patient is not None:
            self.file_number = (patient.file_number or 0) + 1
        else:
            self.file_number = 1

    @cached_property
    def vitals_reference_ranges(self) -> dict[str, tuple[dict[str, Any], ...]]:
        """Return vitals reference ranges for this patient.

        Currently, this just returns the general reference ranges,
        but in the future, we hope to also take age into account.
        E.g. Produce different reference ranges for babies, adolescents,
        adults, and the elderly.
        """
        # import's here due to circular dependency issues
        from sil_advantage.visits.utils import VITALS_REFERENCE_RANGES

        patient_ref_ranges = {}
        for sign, ranges in VITALS_REFERENCE_RANGES.items():
            patient_ref_ranges[sign] = tuple(map(asdict, ranges))
        return patient_ref_ranges

    def clean(self) -> None:
        """Override clean method."""
        if self._state.adding:
            self._generate_file_number()
        super().clean()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Send SMS on patient registration."""
        is_new = self._state.adding
        send_patient_registration = OrganisationSetting.get_setting(
            self.organisation,
            self.branch_id,
            "patients:patient_registration_sms",
        )

        super().save(*args, **kwargs)

        if is_new and send_patient_registration.value:
            send_patient_registration_sms.apply_async(
                queue=settings.CELERY_DEFAULT_QUEUE,
                priority=settings.CELERY_TASK_LOW_PRIORITY,
                args=(self.pk, "PATIENT_REGISTRATION"),
            )


class DocumentTransitionLog(  # type: ignore[django-manager-missing]
    OrgUnitIdsMixin,
    AbstractBase,
):
    """Hold document state transition logs."""

    document = models.ForeignKey(
        "PatientDocument",
        on_delete=models.PROTECT,
        related_name="state_transition_logs",
    )
    document_status = models.CharField(
        max_length=20,
        choices=REVIEW_STATES,
    )
    document_status_from = models.CharField(
        max_length=20,
        choices=REVIEW_STATES,
    )
    document_status_to = models.CharField(
        max_length=20,
        choices=REVIEW_STATES,
    )
    transition_date = models.DateField(auto_now_add=True)

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass


class PatientDocument(
    TransitionValidationMixin,
    AbstractAttachment,
):
    """Document details."""

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="patient_document",
    )
    document_type = models.CharField(
        max_length=100,
        choices=PATIENT_DOCUMENT_TYPES,
    )
    document_number = models.CharField(null=True, blank=True)
    document_status = models.CharField(
        max_length=20,
        choices=REVIEW_STATES,
        default=PENDING,
    )
    rejection_reason = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    # Here for backwards compatibility
    # Otherwise, check the visit itself
    visit_date = models.DateField()

    _transition_graph = DOCUMENT_STATUS_TRANSITION_GRAPH
    _transition_field = "document_status"
    _transition_log_model = DocumentTransitionLog
    _transition_log_model_fk_field = "document"

    organisation_verify = ["patient"]

    objects: models.Manager["PatientDocument"] = CacheableManager()

    class Meta(AbstractBase.Meta):
        """Make ID value unique per ID document type and person."""

        ordering = ("-updated", "-created")


class PatientListUpload(OrgUnitIdsMixin, AbstractBase):
    """Holds patient upload lists.

    Also holds any subsequent system-generated file
    for failed uploads.
    """

    upload_file = models.ForeignKey(
        Attachment, on_delete=models.PROTECT, related_name="+"
    )
    mapping = models.JSONField(
        default=dict, blank=True, help_text="The user-defined excel column mappings"
    )
    success_count = models.IntegerField(default=0)
    fail_count = models.IntegerField(default=0)
    failed_uploads_file = models.ForeignKey(
        Attachment,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    process_state = models.CharField(
        max_length=20, choices=PROCESSING_STATES, default="PENDING"
    )
    upload_type = models.CharField(
        max_length=20, choices=UPLOAD_TYPES, default="GENERAL"
    )
    objects: models.Manager["PatientListUpload"] = CacheableManager()

    class Meta(AbstractBase.Meta):
        """Set model options."""

        ordering = ("-updated", "-created")


class PatientCover(OrgUnitIdsMixin, AbstractBase):
    """Hold patient covers."""

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="patient_covers",
    )
    scheme_name = models.CharField(max_length=255)
    # ID of the scheme on ERP
    scheme_id = models.UUIDField(null=True, blank=True)
    # ID of the customer on ERP
    payer_id = models.UUIDField(null=True, blank=True)
    member_number = models.CharField(max_length=60)
    valid_from = models.DateField(blank=True, null=True)
    valid_to = models.DateField(blank=True, null=True)
    is_principal = models.BooleanField(default=False, blank=True)

    model_validators = ["validate_valid_to_is_greater_than_valid_from"]

    organisation_verify = ["patient"]
    objects: models.Manager["PatientCover"] = CacheableManager()

    def validate_valid_to_is_greater_than_valid_from(self) -> None:
        """Validate valid_to is greater than valid_from."""
        if self.valid_from and self.valid_to:
            if self.valid_to <= self.valid_from:
                raise ValidationError("valid_to must be greater than valid_from")

    class Meta(AbstractBase.Meta):
        """Set model options."""

        unique_together = ("patient", "scheme_id")

    def __str__(self) -> str:
        """String representation of PatientCover: Patients Full Name - Scheme Name."""
        return f"{self.patient.person.get_full_name()} - {self.scheme_name}"
