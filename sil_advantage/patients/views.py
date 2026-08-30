"""Patient app Viewsets."""
import logging
import uuid
from typing import Any

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from sil_edge_connection.exceptions import AuthFailure, RequestFailure

from sil_advantage.common.api_clients import get_health_crm_client
from sil_advantage.common.constants import REVERSE_RELATIONSHIPS
from sil_advantage.common.models import Person, RelatedPerson
from sil_advantage.common.models.common_models import Attachment
from sil_advantage.common.serializers import (
    LinkPersonSerializer,
    RelatedPersonSerializer,
)
from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.common.views.base import CacheableBaseView
from sil_advantage.patients.filters import (
    PatientCoverFilter,
    PatientDocumentAttachmentFilter,
    PatientFilter,
    PatientListUploadFilter,
)
from sil_advantage.patients.models import (
    Patient,
    PatientCover,
    PatientDocument,
    PatientListUpload,
)
from sil_advantage.patients.serializers import (
    PatientCoverSerializer,
    PatientDocumentSerializer,
    PatientHealthIDSerializer,
    PatientListUploadSerializer,
    PatientSerializer,
)
from sil_advantage.integrations.tasks import sync_updates_to_remote
from sil_advantage.patients.tasks import (
    process_patient_list_upload,
    send_health_id_registration_sms,
)
from sil_advantage.permissions import perms, scopes
from sil_advantage.settings.models import OrganisationSetting
from sil_advantage.visits.views import filter_backends

LOGGER = logging.getLogger(__name__)


class PatientViewSet(CacheableBaseView):
    """Patient viewset."""

    permissions = {
        "GET": [perms.PATIENT_VIEW],
        "POST": [perms.PATIENT_CREATE],
        "PATCH": [perms.PATIENT_EDIT],
        "DELETE": [perms.PATIENT_DELETE],
    }
    scopes = {
        "GET": [scopes.PATIENT_READ],
        "POST": [scopes.PATIENT_WRITE],
        "PATCH": [scopes.PATIENT_WRITE],
        "DELETE": [scopes.PATIENT_WRITE],
    }

    queryset = Patient.objects.all().prefetch_related("person__person_contacts")
    _select_related = ["person"]
    _prefetch_related = [
        "person__person_ids",
    ]
    serializer_class = PatientSerializer
    filter_backends = filter_backends

    filterset_class = PatientFilter
    ordering_fields = (
        "person__last_name",
        "person__first_name",
        "person__date_of_birth",
    )
    search_fields = (
        "person__first_name",
        "person__last_name",
        "person__other_names",
        "person__person_contacts__contact",
        "file_number",
        "person__person_ids__id_value",
        "global_health_id",
    )

    _data_partition_field = "organisation"

    @action(
        detail=False,
        methods=["put"],
        permission_classes=[IsAuthenticated],
    )
    def set_health_id(self, request: AuthenticatedRequest) -> Response:
        """Callback to update the patient's health ID as issued by Health CRM."""
        serializer = PatientHealthIDSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        patient = Patient.objects.filter(id=data["profile_id"]).first()

        if patient is None:
            return Response(
                data={"error": "invalid profile id"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        health_id = data["health_id"]
        patient.global_health_id = health_id
        patient.save()
        send_global_health_id_sms = OrganisationSetting.get_org_setting(
            patient.organisation,
            "patients:patient_global_health_id",
        )
        if send_global_health_id_sms.value and len(health_id) != 0:
            send_health_id_registration_sms.apply_async(
                queue=settings.CELERY_DEFAULT_QUEUE,
                priority=settings.CELERY_TASK_LOW_PRIORITY,
                args=(patient.id, "PATIENT_GLOBAL_HEALTH_ID"),
            )

        return Response(data={}, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["POST", "PUT"],
        permission_classes=[IsAuthenticated],
    )
    def link_related(
        self,
        request: AuthenticatedRequest,
        pk: uuid.UUID,
    ) -> Response:
        """Link this patient to a related person."""
        me: Patient = Patient.objects.select_related("person").get(pk=pk)
        with transaction.atomic():
            kwargs: dict[str, Any] = {
                "data": request.data,
                "context": {"request": request},
            }

            related_person_id = request.data.get("id", None)
            if related_person_id is not None:
                kwargs["instance"] = Person.objects.get(id=related_person_id)

            payload = LinkPersonSerializer(**kwargs)
            payload.is_valid(raise_exception=True)
            relationship = payload.validated_data.pop("relationship")
            related_person: Person = payload.save()

            gender_index = {
                "MALE": 0,
                "FEMALE": 1,
                "OTHER": 2,
            }.get(me.person.gender or "OTHER", 2)
            mapping = REVERSE_RELATIONSHIPS.get(
                relationship,
                ("U", "U", "U"),
            )
            reverse_rship = mapping[gender_index]

            relations = []
            if related_person_id is None:
                common_fields = {
                    "organisation": related_person.organisation,
                    "cluster_id": related_person.cluster_id,
                    "branch_id": related_person.branch_id,
                    "department_id": related_person.department_id,
                    "workstation_id": related_person.workstation_id,
                    "created_by": related_person.created_by,
                    "updated_by": related_person.updated_by,
                }
                relation = RelatedPerson(
                    me=me.person,
                    related=related_person,
                    relationship=relationship,
                    **common_fields,
                )
                relations.append(relation)
                relations.append(
                    RelatedPerson(
                        me=related_person,
                        related=me.person,
                        relationship=reverse_rship,
                        **common_fields,
                    )
                )

                RelatedPerson.objects.bulk_create(relations)
            else:
                relation = RelatedPerson.objects.get(
                    me=me.person,
                    related=related_person,
                )
                relation.relationship = relationship
                relations.append(relation)

                reverse_relation = RelatedPerson.objects.get(
                    me=related_person,
                    related=me.person,
                )
                reverse_relation.relationship = reverse_rship
                relations.append(reverse_relation)

                RelatedPerson.objects.bulk_update(relations, ("relationship",))

        data = RelatedPersonSerializer(relation).data
        return Response(data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["GET"],
        permission_classes=[IsAuthenticated],
    )
    def related_persons(
        self,
        request: AuthenticatedRequest,
        pk: uuid.UUID,
    ) -> Response:
        """Return the list of related persons."""
        patient: Patient = self.get_object()
        related = (
            RelatedPerson.objects.filter(me=patient.person)
            .select_related("related")
            .prefetch_related(
                "related__person_contacts",
                "related__person_ids",
            )
        )
        return Response(
            RelatedPersonSerializer(related, many=True).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["POST"],
        permission_classes=[
            IsAuthenticated,
        ],
    )
    def sync_patient_to_clinical(
        self, request: AuthenticatedRequest
    ) -> Response:
        """Re-run the clinical sync for one patient.

        A sync that fails leaves the patient saved but unsynced, so that a
        failure downstream never costs a registration. This is how such a
        patient is sent again once the cause is fixed.
        """
        patient_id = str(request.data.get("patient_id", "")).strip()

        if not patient_id:
            raise ValidationError({"patient_id": "This field is required."})

        patient = get_object_or_404(Patient, id=patient_id)

        sync_updates_to_remote(
            f"{patient._meta.app_label}.{patient._meta.model_name}",
            patient.pk,
            "CLINICAL_SERVICE",
            "UPDATE" if patient.clinical_id else "CREATE",
        )
        patient.refresh_from_db()

        if patient.clinical_id is None:
            return Response(
                {"error": "The patient could not be synced."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {"clinical_id": str(patient.clinical_id)},
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["GET"],
        permission_classes=[
            IsAuthenticated,
        ],
    )
    def person_search(self, request: AuthenticatedRequest) -> Response:
        """Proxy patient search calls to Health-CRM."""
        # HealthCRM is not part of every deployment. Without it there is nothing
        # to match against, which is an empty result rather than an error: the
        # registration form uses this to offer an existing person, and falls
        # through to creating one when there are none.
        if not settings.HEALTH_CRM_API_URL:
            return Response(
                data={"count": 0, "next": None, "previous": None, "results": []},
                status=status.HTTP_200_OK,
            )

        health_crm_client = get_health_crm_client()

        params: dict = request.query_params
        filters = {}
        filters.update(params)

        try:
            resp = health_crm_client.persons.search(params=filters)
            return Response(data=resp, status=status.HTTP_200_OK)
        except (RequestFailure, AuthFailure) as e:
            return Response(e.response, status=e.status_code)

    @action(
        detail=False,
        methods=["GET"],
        permission_classes=[IsAuthenticated],
    )
    def file_upload_fields(self, request: AuthenticatedRequest) -> Response:
        """Return fields required for patient file upload mapping."""
        data = [
            "first_name",
            "last_name",
            "full_name",
            "other_names",
            "phone_number",
            "patient_number",
            "gender",
            "age",
            "date_of_birth",
        ]
        return Response(data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=["POST"],
        permission_classes=[IsAuthenticated],
    )
    def process_file_upload(self, request: AuthenticatedRequest) -> Response:
        """Process a patient list upload request."""
        user = request.user
        data = request.data
        file = request.FILES["file"]
        request.data.pop("file")

        mapping = {}
        for field, column_header in data.items():
            mapping[field] = column_header

        workstation_id = request.META.get("HTTP_X_WORKSTATION") or request.META.get(
            "X-Workstation"
        )
        department_id = request.META.get("HTTP_X_DEPARTMENT") or request.META.get(
            "X-Department"
        )
        branch_id = request.META.get("HTTP_X_BRANCH") or request.META.get("X-Branch")
        cluster_id = request.META.get("HTTP_X_CLUSTER") or request.META.get("X-Cluster")

        common_fields = {
            "organisation": user.organisation,
            "cluster_id": cluster_id,
            "branch_id": branch_id,
            "department_id": department_id,
            "workstation_id": workstation_id,
            "created_by": user.guid,
            "updated_by": user.guid,
        }
        attachment = Attachment.objects.create(
            content_type=file.content_type,
            data=file,
            title=file.name,
            size=file.size,
            **common_fields,
        )

        patient_list_upload = PatientListUpload.objects.create(
            upload_file=attachment,
            mapping=mapping,
            **common_fields,
            process_state="IN_PROGRESS",
            upload_type="GENERAL",
        )

        process_patient_list_upload.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
            args=(patient_list_upload.id,),
        )

        return Response(
            PatientListUploadSerializer(patient_list_upload).data,
            status=status.HTTP_202_ACCEPTED,
        )


class PatientDocumentViewSet(CacheableBaseView):
    """Patient document attachments view."""

    permissions = {
        "GET": [perms.PATIENT_DOCUMENT_VIEW],
        "POST": [perms.PATIENT_DOCUMENT_CREATE],
        "PATCH": [perms.PATIENT_DOCUMENT_EDIT],
        "DELETE": [perms.PATIENT_DOCUMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.PATIENT_READ],
        "POST": [scopes.PATIENT_WRITE],
        "PATCH": [scopes.PATIENT_WRITE],
        "DELETE": [scopes.PATIENT_WRITE],
    }
    queryset = PatientDocument.objects.all()
    filterset_class = PatientDocumentAttachmentFilter
    serializer_class = PatientDocumentSerializer

    _select_related = ["patient", "patient__person"]

    search_fields = (
        "patient__file_number",
        "title",
        "description",
        "document_type",
    )
    parser_classes = (MultiPartParser,)

    _data_partition_field = "organisation"


class PatientCoverViewSet(CacheableBaseView):
    """Patient document attachments view."""

    permissions = {
        "GET": [perms.PATIENT_VIEW],
        "POST": [perms.PATIENT_CREATE],
        "PATCH": [perms.PATIENT_EDIT],
        "DELETE": [perms.PATIENT_DELETE],
    }
    scopes = {
        "GET": [scopes.PATIENT_READ],
        "POST": [scopes.PATIENT_WRITE],
        "PATCH": [scopes.PATIENT_WRITE],
        "DELETE": [scopes.PATIENT_WRITE],
    }
    queryset = PatientCover.objects.all()
    filterset_class = PatientCoverFilter
    serializer_class = PatientCoverSerializer

    _select_related = ["patient", "patient__person"]

    search_fields = (
        "patient__person__first_name",
        "patient__person__last_name",
        "scheme_name",
        "member_number",
    )

    _data_partition_field = "organisation"


class PatientListUploadViewSet(CacheableBaseView):
    """Patient list upload view."""

    permissions = {
        "GET": [perms.PATIENT_LIST_UPLOAD_VIEW],
        "POST": [perms.PATIENT_LIST_UPLOAD_CREATE],
        "PATCH": [perms.PATIENT_LIST_UPLOAD_EDIT],
        "DELETE": [perms.PATIENT_DOCUMENT_DELETE],
    }
    scopes = {
        "GET": [scopes.PATIENT_LIST_UPLOAD_READ],
        "POST": [scopes.PATIENT_LIST_UPLOAD_WRITE],
        "PATCH": [scopes.PATIENT_LIST_UPLOAD_WRITE],
        "DELETE": [scopes.PATIENT_LIST_UPLOAD_WRITE],
    }

    queryset = PatientListUpload.objects.all()
    filterset_class = PatientListUploadFilter
    serializer_class = PatientListUploadSerializer
