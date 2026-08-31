"""Visits models."""

from typing import Any

import pytz
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from sil_cacheable.orm import CacheableManager

from sil_advantage.billing import BILLING_CLASSES
from sil_advantage.common.cache import cached
from sil_advantage.common.models import (
    AbstractBase,
    OrgUnitIdsMixin,
    TransitionValidationMixin,
)
from sil_advantage.config.settings import TIME_ZONE
from sil_advantage.integrations.mixins import RemoteObjectMixin
from sil_advantage.patients.models import Patient
from sil_advantage.practitioners.models import Practitioner
from sil_advantage.scheduling.models import Appointment, Schedule
from sil_advantage.settings.models import OrganisationSetting

# FHIR Encounter Classes
# https://terminology.hl7.org/3.1.0/ValueSet-v3-ActEncounterCode.html
VISIT_TYPES = (
    ("AMB", "Outpatient"),
    ("IMP", "Inpatient"),
    ("EMER", "Emergency"),
    ("FLD", "Field"),
    ("HH", "Home Health"),
    ("ACUTE", "Inpatient Acute"),
    ("NONAC", "Inpatient Non-Acute"),
    ("OBSENC", "Observation Encounter"),
    ("PRENC", "Pre-Admission"),
    ("SS", "Short Stay"),
    ("VR", "Virtual"),
)

# FHIR Encounter Statuses
# https://hl7.org/fhir/valueset-encounter-status.html
VISIT_STATUSES = (
    ("PLANNED", "Planned"),
    ("ARRIVED", "Arrived"),
    ("TRIAGED", "Triaged"),
    ("IN_PROGRESS", "In Progress"),
    ("ON_LEAVE", "On Leave"),
    ("FINISHED", "Finished"),
    ("CANCELLED", "Cancelled"),
    ("ENTERED_IN_ERROR", "Entered In Error"),
    ("UNKNOWN", "Unknown"),
)
VISIT_OPEN_STATES = ("ARRIVED", "TRIAGED", "IN_PROGRESS", "ON_LEAVE")
VISIT_STATUS_TRANSITION_GRAPH = {
    "PLANNED": ["ARRIVED", "CANCELLED"],
    "ARRIVED": ["IN_PROGRESS", "TRIAGED", "CANCELLED"],
    "TRIAGED": ["IN_PROGRESS"],
    "IN_PROGRESS": ["ON_LEAVE", "FINISHED"],
    "ON_LEAVE": ["IN_PROGRESS", "FINISHED"],
    "FINISHED": [],
    "CANCELLED": [],
    "ENTERED_IN_ERROR": [],
    "UNKNOWN": [],
}

# FHIR Request Priority
# https://www.hl7.org/fhir/valueset-request-priority.html
VISIT_PRIORITIES = [
    # The request has normal/routine priority
    ("NORMAL", "Normal"),
    # The request should be actioned promptly
    # Higher priority than normal/routine
    ("URGENT", "Urgent"),
    # The request should be actioned as soon as possible
    # Higher priority than urgent.
    ("ASAP", "As Soon As Possible"),
    # The request should be actioned immediately
    # Highest possible priority. E.g. an emergency.
    ("EMERGENCY", "Emergency"),
]

QUEUE_TYPES = (
    ("TRIAGE", "Triage"),
    ("CONSULTATION", "Consultation"),
    ("LAB", "Laboratory"),
    ("IMAGING", "Imaging"),
    ("PHARMACY", "Pharmacy"),
    ("BILLING", "Billing"),
    ("PROCEDURE", "Procedure"),
    ("OPTICAL", "Optical"),
    ("BREAST CANCER SCREENING", "Breast Cancer Screening"),
    ("CERVICAL CANCER SCREENING", "Cervical Cancer Screening"),
)

SERVICE_REQUEST_STATUSES = (
    # Patient has not joined the queue yet
    ("PENDING", "Pending"),
    # Patient is currently waiting in the queue
    ("WAITING", "Waiting"),
    # Patient is currently being served
    ("IN_PROGRESS", "In Progress"),
    # Patient has been served
    ("COMPLETED", "Completed"),
    # Patient has been temporarily withdrawn but is expected to resume in the future.
    ("ON_HOLD", "On Hold"),
    ("REVOKED", "Revoked"),
    ("ENTERED_IN_ERROR", "Entered In Error"),
)

# Dispatch status for credit billing
VISIT_DISPATCH_STATUS = (
    # Claim is in draft status, not yet dispatched or processed
    ("DRAFT", "Draft"),
    # Claim has been dispatched for processing
    ("DISPATCHED", "Dispatched"),
    # Claim has been successfully paid
    ("PAID", "Paid"),
    # Claim has been rejected, not processed or paid
    ("REJECTED", "Rejected"),
    ("REDISPATCHED", "Redispatched"),
)

VISIT_DISPATCH_STATUS_TRANSITION_GRAPH = {
    "DRAFT": [
        "DISPATCHED",
    ],
    "DISPATCHED": [
        "PAID",
        "REJECTED",
    ],
    "PAID": [],
    "REJECTED": [
        "PAID",
        "REDISPATCHED",
    ],
    "REDISPATCHED": [
        "PAID",
    ],
}


class VisitTransitionLog(AbstractBase):
    """Hold visit state transition logs."""

    visit = models.ForeignKey(
        "Visit",
        on_delete=models.PROTECT,
        related_name="state_transition_logs",
    )
    status = models.CharField(
        max_length=20,
        choices=VISIT_STATUSES,
    )
    status_from = models.CharField(
        max_length=20,
        choices=VISIT_STATUSES,
    )
    status_to = models.CharField(
        max_length=20,
        choices=VISIT_STATUSES,
    )


class Visit(  # type: ignore
    RemoteObjectMixin,
    TransitionValidationMixin,
    OrgUnitIdsMixin,
    AbstractBase,
):
    """Hold information on visits."""

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="visits",
    )
    visit_number = models.CharField(max_length=64, blank=True)
    visit_type = models.CharField(choices=VISIT_TYPES, max_length=10)
    status = models.CharField(choices=VISIT_STATUSES, max_length=20)
    start = models.DateTimeField(default=timezone.now)
    end = models.DateTimeField(null=True, blank=True)
    priority = models.CharField(
        choices=VISIT_PRIORITIES,
        max_length=25,
        default="NORMAL",
    )

    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.PROTECT,
        related_name="visits",
        null=True,
        blank=True,
    )

    billing_class = models.CharField(
        choices=BILLING_CLASSES,
        max_length=10,
    )
    customer_id = models.UUIDField(null=True, blank=True)
    guarantor_id = models.UUIDField(null=True, blank=True)
    patient_cover = models.UUIDField(null=True, blank=True)
    current_queue = models.ForeignKey(
        "Queue",
        on_delete=models.PROTECT,
        related_name="active_visits",
        null=True,
        blank=True,
    )

    # Clinical
    episode_of_care_id = models.UUIDField(null=True, blank=True)

    # Engagement
    post_visit_survey_token = models.CharField(
        max_length=8,
        null=True,
        blank=True,
        unique=True,
    )

    _remote_obj_refs = {
        "CLINICAL_SERVICE": [
            (
                "visit",
                {
                    "episode_of_care_id": "id",
                },
            )
        ],
    }
    async_enabled = settings.VISIT_ASYNC_ENABLED

    _transition_graph = VISIT_STATUS_TRANSITION_GRAPH
    _transition_field = "status"
    _transition_log_model = VisitTransitionLog
    _transition_log_model_fk_field = "visit"

    model_validators = [
        "validate_only_one_visit_open",
        "validate_start_is_before_end",
    ]
    organisation_verify = ["appointment", "current_queue"]

    objects: models.Manager["Visit"] = CacheableManager()
    _related_serialized_models = (
        "billing_payment",
        "billing_billableitem",
        "billing_invoice",
        "billing_clinicalorder",
        "billing_refund",
        "visits_servicerequest",
        "patients_patient",
    )

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Save old values of fields we're interested in."""
        super().__init__(*args, **kwargs)
        self._old_queue_id = self.current_queue_id

    def validate_only_one_visit_open(self) -> None:
        """Validate we have no visit open before starting a new one."""
        if self._state.adding:
            n_open_visits = self.patient.visits.filter(
                status__in=VISIT_OPEN_STATES,
                organisation=self.organisation,
            ).count()
            if n_open_visits > 0:
                raise ValidationError(
                    _(
                        "Please close the patient's %(n_open_visits)s open visit(s) "
                        "before opening a new one."
                    )
                    % {"n_open_visits": n_open_visits}
                )

    def validate_start_is_before_end(self) -> None:
        """Validate start greater than end."""
        error_msg = {"end": (_("The visit end must be greater than its start."))}
        if self.end is not None and self.end < self.start:
            raise ValidationError(error_msg)

    def _generate_visit_number(self) -> None:
        """Generate a visit number."""
        seq_number = Visit.objects.filter(organisation=self.organisation).count() + 1
        setting = OrganisationSetting.get_org_setting(
            self.organisation, "visits:visit_number_format"
        )
        self.visit_number = setting.value.format(
            seq_number=seq_number, created=timezone.now()
        )

    def _set_customer_and_guarantor_id(self) -> None:
        """Set the customer and guarantor id."""
        patient_customer_id = self.patient.customer_id

        if self.customer_id is None:
            self.customer_id = patient_customer_id

        if self.guarantor_id is None:
            self.guarantor_id = patient_customer_id

    def update_appointment_status(self, transition_to: str) -> None:
        """Update the appointment status after the visit status changes."""
        if self.appointment is not None:
            if transition_to == "ARRIVED":
                self.appointment.appointment_status = "ARRIVED"
                self.appointment.save(update_fields=["appointment_status"])
            elif transition_to in ["IN_PROGRESS", "CANCELLED"]:
                self.appointment.appointment_status = "FULFILLED"
                self.appointment.save(update_fields=["appointment_status"])

    @property
    def clinical_service_visit_payload(self) -> dict:
        """Generate a payload to create an episode of care."""
        status = self.status
        if status in VISIT_OPEN_STATES:
            status = "ACTIVE"

        return {
            "episodeOfCare": {
                "status": status.lower(),
                "patientID": str(self.patient.clinical_id),
            }
        }

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates to related resources."""
        # import's here due to cyclic dependency issues
        from sil_advantage.billing.models import ClinicalOrder
        from sil_advantage.visits.tasks import complete_visit

        adding = self._state.adding
        if adding:
            self._generate_visit_number()
            self._set_customer_and_guarantor_id()

        if self.status not in VISIT_OPEN_STATES:
            self.current_queue = None

        previous_state = self._old_transition_value
        new_state = getattr(self, self._transition_field)
        visit_complete = previous_state != new_state and new_state == "FINISHED"

        previous_requests = ServiceRequest.objects.filter(visit=self)

        # Transition status from arrived to in-progress without
        # processing payments for credit visits
        if (
            previous_requests.exists()
            and self.billing_class == "CREDIT"
            and self.status
            in (
                "ARRIVED",
                "TRIAGED",
            )
        ):
            self.status = "IN_PROGRESS"

        super().save(*args, **kwargs)

        model_defaults = {
            "organisation": self.organisation,
            "cluster_id": self.cluster_id,
            "branch_id": self.branch_id,
            "department_id": self.department_id,
            "workstation_id": self.workstation_id,
            "created_by": self.updated_by,
            "updated_by": self.updated_by,
        }

        if visit_complete:
            complete_visit.apply_async(
                queue=settings.CELERY_DEFAULT_QUEUE,
                priority=settings.CELERY_TASK_LOW_PRIORITY,
                args=(self.id,),
            )

        queue_changed = self._old_queue_id != self.current_queue_id
        if queue_changed:
            _old_queue = None
            if self._old_queue_id is not None:
                _old_queue = Queue.objects.get(pk=self._old_queue_id)
            QueueTransitionLog.objects.create(
                visit=self,
                source=_old_queue,
                destination=self.current_queue,
                **model_defaults,
            )

        if (queue_changed or adding) and self.current_queue is not None:
            if previous_requests.exists():
                previous = previous_requests.latest("created")
                previous.status = "COMPLETED"
                previous.save(update_fields=["status"])

            with transaction.atomic():
                service_request = ServiceRequest.objects.create(
                    visit=self,
                    queue=self.current_queue,
                    **model_defaults,
                )

                ClinicalOrder.objects.create(
                    service_request=service_request,
                    **model_defaults,
                )

        self._old_queue_id = self.current_queue_id
        self.update_appointment_status(self.status)


class VisitDispatchTransitionLog(AbstractBase):
    """Hold visit dispatch status transition logs."""

    visit_dispatch = models.ForeignKey(
        "VisitDispatch",
        on_delete=models.PROTECT,
        related_name="visit_dispatch_transition_logs",
    )
    status_from = models.CharField(
        max_length=20,
        choices=VISIT_DISPATCH_STATUS,
    )
    status_to = models.CharField(
        max_length=20,
        choices=VISIT_DISPATCH_STATUS,
    )


class VisitDispatch(AbstractBase):
    """Hold information about a visits' dispatch."""

    status = models.CharField(
        choices=VISIT_DISPATCH_STATUS, max_length=20, default="DRAFT"
    )
    date_added = models.DateField()
    visit = models.ForeignKey(
        Visit,
        on_delete=models.PROTECT,
    )

    # visitdispatch status transition graph
    _transition_graph = VISIT_DISPATCH_STATUS_TRANSITION_GRAPH
    _transition_field = "status"
    _transition_log_model = VisitDispatchTransitionLog
    _transition_log_model_fk_field = "visit_dispatch"


class Queue(OrgUnitIdsMixin, AbstractBase):  # type: ignore[django-manager-missing]
    """Hold information about queues."""

    name = models.CharField(max_length=255)
    queue_type = models.CharField(choices=QUEUE_TYPES, max_length=50)
    practitioner = models.ForeignKey(
        Practitioner,
        on_delete=models.PROTECT,
        related_name="practitioner_queues",
        null=True,
        blank=True,
    )

    # This will hold queues created automatically per schedule
    schedule = models.OneToOneField(
        Schedule,
        on_delete=models.PROTECT,
        related_name="queue",
        null=True,
        blank=True,
    )

    organisation_verify = ["schedule"]

    objects: models.Manager["Queue"] = CacheableManager()
    _related_serialized_models = ("visits_visit",)

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass


class QueueTransitionLog(OrgUnitIdsMixin, AbstractBase):
    """Hold information about queue transitions."""

    visit = models.ForeignKey(
        Visit,
        on_delete=models.PROTECT,
        related_name="queue_transition_logs",
    )
    # can be null when starting a visit, etc
    source = models.ForeignKey(
        Queue,
        on_delete=models.PROTECT,
        related_name="source_queues",
        null=True,
        blank=True,
    )
    # can be null when closing a visit, etc
    destination = models.ForeignKey(
        Queue,
        on_delete=models.PROTECT,
        related_name="destination_queues",
        null=True,
        blank=True,
    )

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass

    @cached_property
    @cached(key_attr="id")
    def source_queue_name(self) -> str:
        """Return the source queue's name."""
        if self.source_id is None:
            return "None"
        assert self.source is not None
        return self.source.name

    @cached_property
    @cached(key_attr="id")
    def destination_queue_name(self) -> str:
        """Return the destination queue's name."""
        if self.destination_id is None:
            return "None"
        assert self.destination is not None
        return self.destination.name


class ServiceRequest(  # type: ignore
    RemoteObjectMixin,
    OrgUnitIdsMixin,
    AbstractBase,
):
    """Hold information about service requests.

    Based loosely on `https://build.fhir.org/servicerequest.html`.
    """

    visit = models.ForeignKey(
        Visit,
        on_delete=models.PROTECT,
        related_name="service_requests",
    )
    queue = models.ForeignKey(
        Queue,
        on_delete=models.PROTECT,
        related_name="service_requests",
    )
    note = models.TextField(null=True, blank=True)
    status = models.CharField(
        choices=SERVICE_REQUEST_STATUSES,
        default="WAITING",
        max_length=50,
    )
    priority = models.CharField(
        choices=VISIT_PRIORITIES,
        max_length=25,
        default="NORMAL",
    )
    occurrence = models.DateTimeField(null=True, blank=True)

    # Clinical
    encounter_id = models.UUIDField(null=True, blank=True)

    _remote_obj_refs = {
        "CLINICAL_SERVICE": [
            (
                "encounter",
                {
                    "encounter_id": "id",
                },
            )
        ],
    }
    # When starting a visit & adding the patient to a queue
    # simultaneously, we need to delay the creation of the
    # encounter to ensure that the episode of care has
    # already be created
    sync_eta: int = 4
    async_enabled = settings.VISIT_ASYNC_ENABLED

    organisation_verify = ["visit", "queue"]

    objects: models.Manager["ServiceRequest"] = CacheableManager()
    _related_serialized_models = (
        "billing_payment",
        "billing_billableitem",
        "billing_invoice",
        "billing_clinicalorder",
        "billing_refund",
        "patients_patient",
    )

    class Meta(AbstractBase.Meta):
        """Set model options."""

        ordering = ("created", "updated")

    def get_occurrence(self) -> None:
        """Set the occurrence date and default current time."""
        created = self.created or timezone.now()
        start = self.visit.start

        local_tz = pytz.timezone(TIME_ZONE)
        # Visit start date fetched from db is in UTC.
        # Hence the need to localize the date before combining with created time
        localized_start = start.astimezone(local_tz)

        # combines the start data and the created time into a datetime object
        combined_date = created.replace(
            day=localized_start.day,
            month=localized_start.month,
            year=localized_start.year,
        )
        self.occurrence = combined_date

    @cached_property
    @cached(key_attr="id")
    def previous_queue_name(self) -> str:
        """Get the name of the previous queue."""
        log = (
            QueueTransitionLog.objects
            .filter(visit=self.visit_id, destination=self.queue_id)
            .latest("created")
        )  # fmt: skip
        return log.source_queue_name

    @property
    def clinical_service_encounter_payload(self) -> dict:
        """Generate a payload to create an encounter."""
        if self.encounter_id is None:
            return {"episodeID": str(self.visit.episode_of_care_id)}

        if self.status in ("REVOKED", "ENTERED_IN_ERROR"):
            status = "finished"
        else:
            status = "in_progress"
        return {
            "input": {
                "status": status,
            }
        }

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Auto-create a DRAFT invoice for every service request."""
        # import's here due to circular dependency issues
        from sil_advantage.billing.models import Invoice

        adding = self._state.adding
        if adding:
            self.get_occurrence()
        super().save(*args, **kwargs)

        if adding:
            Invoice.objects.create(
                service_request=self,
                workflow_state="DRAFT",
                organisation=self.organisation,
                cluster_id=self.cluster_id,
                branch_id=self.branch_id,
                department_id=self.department_id,
                workstation_id=self.workstation_id,
                created_by=self.created_by,
                updated_by=self.updated_by,
            )


class SurveyResponse(AbstractBase):
    """Hold post visit survey responses."""

    visit = models.OneToOneField(
        Visit,
        on_delete=models.PROTECT,
        related_name="survey_response",
    )
    response = models.JSONField()

    objects: models.Manager["SurveyResponse"] = CacheableManager()
