"""Registration views."""
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from sil_edge_connection.exceptions import AuthFailure, RequestFailure

from sil_advantage.common import filters, models, serializers
from django.utils.crypto import get_random_string

from sil_advantage.common.utilities.provisioning import (
    ProvisioningError,
    provision_organisation,
    provisioning_summary,
)
from sil_advantage.common.api_clients import (
    get_auth_server_api_connection,
    get_chargemaster_client,
)
from sil_advantage.common.constants import (
    ORGANISATION_DOES_NOT_EXIST_CODE,
    ORGANISATION_EXISTS_CODE,
)
from sil_advantage.common.models import Organisation
from sil_advantage.common.views.base import CacheableBaseView
from sil_advantage.permissions import constants
from sil_advantage.sil_auth.models import SILUser

LOGGER = logging.getLogger(__name__)


class OnboardingViewSet(ViewSet):
    """Onboarding Viewset."""

    def _get_default_roles(self) -> dict:
        """Default roles assigned to a new admin during setup.

        The roles include both ERP and Advantage permissions.
        NB: The ERP perms are in a convenience file compiled from ERP
        Any permission updates should also be done here to avoid inconsistencies
        """
        return {
            "Organisation Admin": constants.ERP_ORGANISATION_ADMIN,
            "Store Manager": constants.ERP_STORE_MANAGER,
            "Procurement Manager": constants.ERP_PROCUREMENT_MANAGER,
            "Accountant": constants.ERP_ACCOUNTANT,
            "Sales Manager": constants.ERP_SALES_MANAGER,
            "Sales Clerk": constants.ERP_SALES_CLERK,
            "Advantage Admin": constants.ADVANTAGE_ORGANISATION_ADMIN,
        }

    @action(
        detail=False,
        methods=["GET"],
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def provider_search(self, request: Request) -> Response:
        """Proxy business partner search calls to Charge Master."""
        chargemaster_client = get_chargemaster_client()
        params = request.query_params
        filters: dict = {
            "active": True,
            "fields": "id,slade_code,slade_code_counter,name",
            "bp_type": "PROVIDER",
            "is_branch": False,
        }
        filters.update(params)
        try:
            resp = chargemaster_client.business_partners.list(filters=filters)
            return Response(data=resp, status=status.HTTP_200_OK)
        except (RequestFailure, AuthFailure) as e:
            return Response(e.response, status=e.status_code)

    @action(
        detail=False,
        methods=["GET"],
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def available_countries(self, request: Request) -> Response:
        """Proxy country list call to Charge Master."""
        chargemaster_client = get_chargemaster_client()
        try:
            filters: dict = {"fields": "id,name"}
            resp = chargemaster_client.countries.list(filters=filters)
            return Response(data=resp, status=status.HTTP_200_OK)
        except (RequestFailure, AuthFailure) as e:
            return Response(e.response, status=e.status_code)

    @action(
        detail=False,
        methods=["POST"],
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def organisation_check(self, request: Request) -> Response:
        """Check if a user can proceed to registration.

        Validates whether the organization exists on advantage. If the org exists,
        the user is directed to be added to the org by their admin. The response
        includes a code and a message for consistent frontend redirection.

        Note: Changing the response code requires collaboration between the frontend
        and backend. Currently, the codes are:
                    1: Org exists on advantage
                    2: Org does not exist on advantage(can proceed to registration)

        Returns:
            Response: a code and data indicating whether the organisation exists.
        """
        data: dict = request.data

        slade_code: str | None = data.get("slade_code", None)
        org_name = data.get("name")

        if org_name is None:
            raise ValidationError({"name": "This field is required."})

        org_exists = Organisation.objects.filter(
            Q(slade_code=slade_code) | Q(organisation_name__iexact=org_name)
        ).exists()

        # codes are agreed between frontend and backend
        org_exists_response = {
            "code": ORGANISATION_EXISTS_CODE,
            "message": "Organisation already exists",
        }
        if org_exists:
            return Response(
                status=status.HTTP_200_OK,
                data=org_exists_response,
            )

        org_not_exists_response = {
            "code": ORGANISATION_DOES_NOT_EXIST_CODE,
            "message": "Organisation does not exist",
        }
        return Response(status=status.HTTP_200_OK, data=org_not_exists_response)

    @action(
        detail=False,
        methods=["POST"],
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    @transaction.atomic
    def registration(self, request: Request) -> Response:
        """Provider and admin registration."""
        serializer = serializers.RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        registration_input: dict = serializer.validated_data
        provider_input: dict = registration_input["provider"]

        slade_code: str | None = provider_input.get("slade_code", None)
        if not slade_code:
            chargemaster_client = get_chargemaster_client()
            bp_data = {
                "name": provider_input["name"],
                "bp_type": "PROVIDER",
                "country": provider_input["country_id"],
                "meta_data": {
                    "created_by": "Slade360Advantage",
                },
            }

            try:
                cm_bp = chargemaster_client.business_partners.create(bp_data)
            except (RequestFailure, AuthFailure) as e:
                return Response(e.response, status=e.status_code)

            slade_code = str(cm_bp["slade_code_counter"])

        authserver_client = get_auth_server_api_connection()

        # create the admin user
        try:
            user_data = {
                "first_name": registration_input["first_name"],
                "last_name": registration_input["last_name"],
                "email": registration_input["email"],
                "password": registration_input["password"],
                "confirm_password": registration_input["password"],
                "is_new_org_user": True,
                "default_roles": self._get_default_roles(),
                "agreed_to_terms": True,
                "change_pass_at_next_login": False,
                "org_slade_code": slade_code,
                "sync_business_partner": True,
            }

            as_response = authserver_client.call(
                "/v1/user/user_roles/", method="POST", payload=user_data
            )

        except (RequestFailure, AuthFailure) as e:
            return Response(e.response, status=e.status_code)

        # Set network admin as the created_by and updated_by fields
        admin_email = settings.SYSTEM_ADMIN_EMAIL
        system_admin = SILUser.objects.get(email=admin_email).id

        org_data = {
            "organisation_name": provider_input["name"],
            "slade_code": slade_code,
            "email_address": registration_input["email"],
            "phone_number": registration_input["phone_number"],
            "financial_year_start_date": timezone.now().date().replace(month=1, day=1),
            "created_by": system_admin,
            "updated_by": system_admin,
        }

        # performs the additional setups on ERP, Clinical in save() method
        models.Organisation.objects.create(**org_data)

        return Response(as_response, status=status.HTTP_201_CREATED)


    @action(
        detail=False,
        methods=["POST"],
        permission_classes=[AllowAny],
        authentication_classes=[],
        url_path="facility_registration",
    )
    def facility_registration(self, request: Request) -> Response:
        """Register a facility and its first admin.

        The `registration` action above reaches Chargemaster for a slade code,
        the Slade auth server for the user, and the ERP for the branches and
        workstations that become queues. This does the same work directly, for
        deployments that run none of them.
        """
        serializer = serializers.FacilityRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        owner = payload["owner"]

        if Organisation.objects.filter(
            organisation_name__iexact=payload["name"]
        ).exists():
            raise ValidationError(
                {"name": "An organisation with this name already exists."}
            )

        password = get_random_string(12)

        try:
            result = provision_organisation(
                name=payload["name"],
                email=owner["email"],
                phone=owner.get("phone") or "",
                first_name=owner["first_name"],
                last_name=owner["last_name"],
                password=password,
                address=payload.get("county") or "Nairobi",
            )
        except ProvisioningError as error:
            LOGGER.exception("could not provision %s", payload["name"])

            return Response(
                {"detail": str(error)}, status=status.HTTP_502_BAD_GATEWAY
            )

        body = provisioning_summary(result)
        # No mail is sent from this deployment, so the caller has to be told the
        # credential once, here.
        body["temporary_password"] = password

        return Response(body, status=status.HTTP_201_CREATED)


class OrganisationOnboardingViewSet(CacheableBaseView):
    """Viewset for OrganisationOnboarding."""

    queryset = models.OrganisationOnboarding.objects.all()
    serializer_class = serializers.OrganisationOnboardingSerializer
    filterset_class = filters.OrganisationOnboardingfilter
