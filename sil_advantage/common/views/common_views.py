"""Common model views."""
import logging
import uuid
from collections import OrderedDict
from typing import Any, Optional
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import UpdateAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from sil_transitions import TransitionViewMixin

from sil_advantage.common import filters, models, serializers, types
from sil_advantage.common.models.common_models import OperatingRegion
from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.common.utilities import paginate_response
from sil_advantage.common.utilities.misc import generate_otp
from sil_advantage.common.views.base import (
    BaseView,
    CacheableBaseView,
    OrganisationTransitionMixin,
)
from sil_advantage.notifications.sms.tasks import send_sms
from sil_advantage.patients.tasks import (
    send_patient_communication_consent_otp_sms,
)
from sil_advantage.permissions import perms, scopes
from sil_advantage.sil_auth.permission_classes import IsNetworkAdmin

LOGGER = logging.getLogger(__file__)


class OrganisationViewSet(OrganisationTransitionMixin, BaseView):
    """Organisations view."""

    export_fields = OrderedDict(
        [
            (
                "organisation_name",
                {"label": "Client Name", "format": "capitalize"},
            ),
            ("phone_number", {"label": "Phone Number"}),
            ("email_address", {"label": "E-mail Address"}),
            ("active", {"label": "Active?", "format": "boolean"}),
        ]
    )
    permissions = {
        "GET": [perms.ORGANISATION_VIEW],
        "POST": [perms.ORGANISATION_CREATE],
        "PATCH": [perms.ORGANISATION_EDIT],
        "DELETE": [perms.ORGANISATION_DELETE],
    }
    scopes = {
        "GET": [scopes.ORGANISATION_READ],
        "POST": [scopes.ORGANISATION_WRITE],
        "PATCH": [scopes.ORGANISATION_WRITE],
        "DELETE": [scopes.ORGANISATION_WRITE],
    }

    queryset = models.Organisation.objects.all()
    serializer_class = serializers.OrganisationSerializer
    filterset_class = filters.OrganisationFilter
    ordering_fields = (
        "organisation_name",
        "slade_code",
        "email_address",
    )
    search_fields = (
        "organisation_name",
        "email_address",
        "slade_code",
    )
    transition_field = "active"

    _data_partition_field = None

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def setup_organisation(
        self,
        request: types.AuthenticatedRequest,
    ) -> Response:
        """Create a new organisation.

        Very thin, org setup should be done on the ERP.
        """
        context = {"request": request}
        serializer = serializers.OrganisationSerializer(
            data=request.data, context=context
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["GET", "PATCH"])
    @transaction.atomic
    def update_organisation(
        self,
        request: types.AuthenticatedRequest,
        pk: Optional[UUID] = None,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Update an organisation on this server."""
        kwargs["pk"] = pk
        context = {"request": request}
        if request.method == "GET":
            return super().retrieve(request, *args, **kwargs)
        organisation = self.get_object()
        serializer = self.get_serializer(
            organisation, data=request.data, partial=True, context=context
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(data=serializer.data, status=status.HTTP_200_OK)

    def update(
        self,
        request: types.AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Skip ``TransitionViewMixin``s update which calls self.transition."""
        return super(BaseView, self).update(request, *args, **kwargs)

    @action(
        detail=True,
        methods=["patch"],
        url_path=r"transition/(?P<organisation_state>\w+)",
        permission_classes=(IsNetworkAdmin,),
    )
    def transition(
        self, request: types.AuthenticatedRequest, pk: UUID, organisation_state: str
    ) -> Response:
        """Move an organisation to a different status."""
        return super().transition(request, pk=pk, active=organisation_state)

    @action(detail=True, methods=["get"], url_path="transition_history")
    def transition_history(
        self,
        request: types.AuthenticatedRequest,
        pk: UUID,
    ) -> Response:
        """View an organisation's transition history."""
        log_objs = self.get_object().organisation_logs.all()
        return paginate_response(self, log_objs, serializers.OrgTransitionLogSerializer)


class PersonViewSet(CacheableBaseView):
    """Person view."""

    permissions = {
        "GET": [perms.PERSON_VIEW],
        "POST": [perms.PERSON_CREATE],
        "PATCH": [perms.PERSON_EDIT],
        "DELETE": [perms.PERSON_DELETE],
    }
    scopes = {
        "GET": [scopes.PERSON_READ],
        "POST": [scopes.PERSON_WRITE],
        "PATCH": [scopes.PERSON_WRITE],
        "DELETE": [scopes.PERSON_WRITE],
    }

    queryset = models.Person.objects.all().prefetch_related("person_contacts")
    _select_related = []
    _prefetch_related = [
        "person_ids",
    ]
    serializer_class = serializers.PersonSerializer

    filterset_class = filters.PersonFilter
    ordering_fields = ("first_name", "last_name", "date_of_birth")
    search_fields = ("first_name", "last_name", "other_names")

    _data_partition_field = "organisation"

    def create(
        self, request: AuthenticatedRequest, *args: Any, **kwargs: Any
    ) -> Response:
        """Person registration and validation."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Perform validation check
        first_name = serializer.validated_data["first_name"]
        last_name = serializer.validated_data["last_name"]
        date_of_birth = serializer.validated_data.get("date_of_birth")
        contacts = serializer.validated_data.get("person_contacts", [])
        if contacts:
            for contact in contacts:
                phone_number = contact.get("contact")
                if models.Person.objects.filter(
                    first_name=first_name,
                    last_name=last_name,
                    person_contacts__contact=phone_number,
                ).exists():
                    raise ValidationError(
                        "Person with matching details already exists."
                    )
        else:
            if models.Person.objects.filter(
                first_name=first_name, last_name=last_name, date_of_birth=date_of_birth
            ).exists():
                raise ValidationError("Person with matching details already exists.")
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )


class RelatedPersonViewSet(CacheableBaseView):
    """RelatedPerson view."""

    permissions = {
        "GET": [perms.PERSON_VIEW],
        "POST": [perms.PERSON_CREATE],
        "PATCH": [perms.PERSON_EDIT],
        "DELETE": [perms.PERSON_DELETE],
    }
    scopes = {
        "GET": [scopes.PERSON_READ],
        "POST": [scopes.PERSON_WRITE],
        "PATCH": [scopes.PERSON_WRITE],
        "DELETE": [scopes.PERSON_WRITE],
    }

    queryset = models.RelatedPerson.objects.all().prefetch_related(
        "related__person_contacts"
    )
    _select_related = ["related"]
    _prefetch_related = [
        "related__person_ids",
    ]
    serializer_class = serializers.RelatedPersonSerializer

    filterset_class = filters.RelatedPersonFilter

    _data_partition_field = "organisation"


class PersonContactViewSet(CacheableBaseView):
    """Person contact view."""

    permissions = {
        "GET": [perms.PERSON_VIEW],
        "POST": [perms.PERSON_CREATE],
        "PATCH": [perms.PERSON_EDIT],
        "DELETE": [perms.PERSON_DELETE],
    }
    scopes = {
        "GET": [scopes.PERSON_READ],
        "POST": [scopes.PERSON_WRITE],
        "PATCH": [scopes.PERSON_WRITE],
        "DELETE": [scopes.PERSON_WRITE],
    }
    queryset = models.PersonContact.objects.all()
    serializer_class = serializers.PersonContactSerializer
    filterset_class = filters.PersonContactFilter
    search_fields = (
        "contact_type",
        "contact",
        "person__first_name",
        "person__last_name",
        "person__other_names",
    )

    _data_partition_field = "organisation"


class PersonIDViewSet(CacheableBaseView):
    """Person ID view."""

    permissions = {
        "GET": [perms.PERSON_VIEW],
        "POST": [perms.PERSON_CREATE],
        "PATCH": [perms.PERSON_EDIT],
        "DELETE": [perms.PERSON_DELETE],
    }
    scopes = {
        "GET": [scopes.PERSON_READ],
        "POST": [scopes.PERSON_WRITE],
        "PATCH": [scopes.PERSON_WRITE],
        "DELETE": [scopes.PERSON_WRITE],
    }
    queryset = models.PersonID.objects.all()
    serializer_class = serializers.PersonIDSerializer
    filterset_class = filters.PersonIDFilter
    search_fields = (
        "id_document_type",
        "id_value",
        "person__first_name",
        "person__last_name",
        "person__other_names",
    )

    _data_partition_field = "organisation"


class PersonAttachmentViewSet(BaseView):
    """Person attachment view."""

    permissions = {
        "GET": [perms.PERSON_VIEW],
        "POST": [perms.PERSON_CREATE],
        "PATCH": [perms.PERSON_EDIT],
        "DELETE": [perms.PERSON_DELETE],
    }
    scopes = {
        "GET": [scopes.PERSON_READ],
        "POST": [scopes.PERSON_WRITE],
        "PATCH": [scopes.PERSON_WRITE],
        "DELETE": [scopes.PERSON_WRITE],
    }
    queryset = models.PersonAttachment.objects.all()
    serializer_class = serializers.PersonAttachmentSerializer
    parser_classes = (MultiPartParser,)
    filterset_class = filters.PersonAttachmentFilter
    search_fields = (
        "title",
        "description",
        "person__first_name",
        "person__last_name",
        "person__other_names",
    )

    _data_partition_field = "organisation"


class UserProfileViewSet(BaseView):
    """User profile view."""

    permissions = {
        "GET": [perms.USER_PROFILE_VIEW],
        "POST": [perms.USER_PROFILE_CREATE],
        "PATCH": [perms.USER_PROFILE_EDIT],
        "DELETE": [perms.USER_PROFILE_DELETE],
    }
    scopes = {
        "GET": [scopes.USER_PROFILE_READ],
        "POST": [scopes.USER_PROFILE_WRITE],
        "PATCH": [scopes.USER_PROFILE_WRITE],
        "DELETE": [scopes.USER_PROFILE_WRITE],
    }
    permission_classes = (IsAuthenticated,)
    queryset = models.UserProfile.objects.all()
    serializer_class = serializers.UserProfileSerializer
    filterset_class = filters.UserProfileFilter
    search_fields = (
        "user__email",
        "person__first_name",
        "person__last_name",
        "person__other_names",
    )

    _data_partition_field = "organisation"


class PractitionerViewSet(BaseView):
    """Practitoner view."""

    permissions = {
        "GET": [perms.PERSON_VIEW],
        "POST": [perms.PERSON_CREATE],
        "PATCH": [perms.PERSON_EDIT],
        "DELETE": [perms.PERSON_DELETE],
    }

    scopes = {
        "GET": [scopes.PERSON_READ],
        "POST": [scopes.PERSON_WRITE],
        "PATCH": [scopes.PERSON_WRITE],
        "DELETE": [scopes.PERSON_WRITE],
    }

    queryset = models.Practitioner.objects.all()
    serializer_class = serializers.PractitionerSerializer
    filterset_class = filters.Practitionerfilter
    search_fields = (
        "person__first_name",
        "person__last_name",
        "person__other_names",
        "qualification",
    )

    _data_partition_field = "organisation"


class ConsentViewSet(BaseView):
    """Consent viewset."""

    permissions = {
        "GET": [perms.PERSON_VIEW],
        "POST": [perms.PERSON_CREATE],
        "PATCH": [perms.PERSON_EDIT],
        "DELETE": [perms.PERSON_DELETE],
    }

    scopes = {
        "GET": [scopes.PERSON_READ],
        "POST": [scopes.PERSON_WRITE],
        "PATCH": [scopes.PERSON_WRITE],
        "DELETE": [scopes.PERSON_WRITE],
    }

    queryset = models.Consent.objects.all()
    serializer_class = serializers.ConsentSerializer
    filterset_class = filters.ConsentFilter

    _data_partition_field = "organisation"

    @action(
        detail=True,
        methods=["POST"],
    )
    def send_otp(self, request: AuthenticatedRequest, pk: uuid.UUID) -> Response:
        """Sends a user an OTP message to their phone."""
        consent_obj = self.get_object()

        user = request.user
        person = consent_obj.person

        data = {
            "person": person,
            "code": generate_otp(),
            "organisation": person.organisation,
            "branch_id": person.branch_id,
            "created_by": user.id,
            "updated_by": user.id,
        }
        otp_obj = models.PersonOTP.objects.create(**data)

        consent_obj.otp = otp_obj
        consent_obj.save()

        if consent_obj.consent_type == models.ConsentType.SMS_COMMUNICATION:
            send_patient_communication_consent_otp_sms.apply_async(
                queue=settings.CELERY_DEFAULT_QUEUE,
                priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
                args=(person.id, "PATIENT_COMMUNICATION_CONSENT_OTP", otp_obj.code),
            )
        else:
            message = (
                f"Hi {person.first_name}, your consent verification code is "
                f"{otp_obj.code}. Never share this code."
            )
            send_sms.apply_async(
                queue=settings.CELERY_DEFAULT_QUEUE,
                priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
                args=(
                    "OTP",
                    message,
                    [person.phone_number],
                    person.organisation.slade_code,
                    person.branch_id,
                    person.workstation_id,
                ),
            )

        serializer = self.get_serializer(consent_obj)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["POST"],
    )
    def verify_otp(self, request: AuthenticatedRequest, pk: uuid.UUID) -> Response:
        """Sends a user an OTP message to their phone."""
        serializer = serializers.OTPVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.data["code"]

        consent_obj = self.get_object()
        otp_obj = consent_obj.otp

        try:
            otp_obj.verify_otp_code(code)
        except ModelValidationError as e:
            raise ValidationError(e.messages)

        return Response(
            {"status": models.OTPVerificationStatus.VERIFIED}, status=status.HTTP_200_OK
        )


class ConsentTransitionView(TransitionViewMixin, UpdateAPIView):
    """Consent Transition API View."""

    queryset = models.Consent.objects.all()
    serializer_class = serializers.ConsentSerializer
    lookup_field = "id"
    transition_graph = models.CONSENT_STATUS_TRANSITION_GRAPH
    transition_field = "status"
    transition_log_serializer = serializers.ConsentTransitionLogSerializer


class OperatingRegionViewSet(CacheableBaseView):
    """OperatingRegion instances view."""

    permissions = {
        "GET": [perms.OPERATING_REGION_VIEW],
        "POST": [perms.OPERATING_REGION_CREATE],
        "PATCH": [perms.OPERATING_REGION_EDIT],
        "DELETE": [perms.OPERATING_REGION_DELETE],
    }

    scopes = {
        "GET": [scopes.OPERATING_REGION_READ],
        "POST": [scopes.OPERATING_REGION_WRITE],
        "PATCH": [scopes.OPERATING_REGION_WRITE],
        "DELETE": [scopes.OPERATING_REGION_WRITE],
    }

    permission_classes = (IsAuthenticated,)
    queryset = OperatingRegion.objects.all()
    serializer_class = serializers.OperatingRegionSerializer
    filterset_class = filters.OperatingRegionFilter
    search_fields = (
        "name",
        "country",
        "unit_type",
    )

    _data_partition_field = "organisation"
