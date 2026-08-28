"""Authentication views."""
import copy
import uuid
from collections import OrderedDict
from typing import Any, Optional, Sequence

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from sil_advantage.common.api_clients import auth_server, make_request
from sil_advantage.common.models import OTPVerificationStatus, PersonOTP
from sil_advantage.common.serializers import OTPVerificationSerializer
from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.common.utilities.misc import generate_otp
from sil_advantage.common.views.base import BaseView
from sil_advantage.notifications.sms.tasks import send_sms
from sil_advantage.permissions import perms as perms
from sil_advantage.sil_auth import filters
from sil_advantage.sil_auth.auth_utils import generate_rand_password
from sil_advantage.sil_auth.models import MFAStatus, SILUser, SILUserMFA
from sil_advantage.sil_auth.serializers import UserMFASerializer, UserSerializer


def page_size_auth_server(
    query_params: dict[str, Any],
) -> dict[str, Optional[int]]:
    """Determine how many records to ask for at a time from auth server."""
    if query_params.get("page_size"):
        return {"page_size": query_params.get("page_size")}
    else:
        return {"page_size": api_settings.PAGE_SIZE}


def extra_perms_from_name(templates: list[dict]) -> list[str]:
    """Combine permissions from various names into one list."""
    all_perms = []
    for t in templates:
        perm_array = getattr(perms.shortcuts, t["id"].upper(), [])
        for p in perm_array:
            if isinstance(p, str):
                all_perms.append(p)
            else:
                all_perms.append(p[0])
    return []


class UserPartitionByOrganisationMixin(generics.GenericAPIView):
    """Filter the user queryset by organisation if they are not a network admin."""

    request: AuthenticatedRequest

    def get_queryset(self) -> QuerySet[SILUser]:
        """Return a filtered user qs depending on the user's role and org."""
        query_set = super().get_queryset()
        org = self.request.user.organisation
        is_network_admin = self.request.user.has_permissions(
            [perms.CROSS_NETWORK_ADMIN[0]]
        )
        if is_network_admin:
            return query_set

        filtered_query_set = query_set.filter(userprofile__organisation=org)

        return filtered_query_set


class UserListCreateView(
    UserPartitionByOrganisationMixin,
    generics.ListAPIView,
):
    """Users' list and create view."""

    permission_classes = (IsAuthenticated,)
    export_fields = OrderedDict(
        [
            ("first_name", {"label": "First Name", "format": "capitalize"}),
            ("last_name", {"label": "Last Name", "format": "capitalize"}),
            ("email", {"label": "Email"}),
        ]
    )

    queryset = get_user_model().objects.all()
    filterset_class = filters.SILUserFilter
    serializer_class = UserSerializer
    search_fields = (
        "userprofile__person__first_name",
        "userprofile__person__last_name",
        "email",
    )
    ordering_fields = (
        "userprofile__person__first_name",
        "userprofile__person__last_name",
        "email",
    )

    def post(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Create a user on both this server and auth server."""
        password = generate_rand_password()
        data = copy.deepcopy(request.data)
        roles = data.pop("user_roles", [])
        data["roles"] = [role["id"] for role in roles]
        data["password"] = password
        data["agreed_to_terms"] = True
        data["change_pass_at_next_login"] = True
        data["confirm_password"] = password
        url = auth_server.USERS_SPECIAL
        resp, status_code = make_request("post", url, request, data)
        if status_code == 201:
            assert isinstance(resp, dict)
            resp_temp = copy.deepcopy(resp)
            resp_temp["password"] = password
            s = UserSerializer(data=resp_temp, context={"request": request})
            s.is_valid(raise_exception=True)
            u_instance = s.save()
            resp["user_id"] = u_instance.id
        return Response(data=resp, status=status_code)


class UserRetrieveUpdateView(
    UserPartitionByOrganisationMixin, generics.RetrieveAPIView
):
    """View to retrieve and update users."""

    permission_classes = (IsAuthenticated,)
    queryset = get_user_model().objects.all()
    serializer_class = UserSerializer
    search_fields: Sequence[str] = []  # not needed
    lookup_field = "guid"

    def get(
        self,
        request: AuthenticatedRequest,
        guid: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Retrieve user details from auth server."""
        api_url = auth_server.USERS_SPECIAL + guid + "/"
        resp, status_code = make_request("get", api_url, request)
        assert isinstance(resp, dict)
        instance = self.get_object()
        resp["user_id"] = instance.id
        return Response(data=resp, status=status_code)

    def patch(
        self,
        request: AuthenticatedRequest,
        guid: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Update user details on auth server."""
        context = {"request": request}
        instance = self.get_object()
        api_url = auth_server.USERS_SPECIAL + guid + "/"
        data = request.data
        roles = data.pop("user_roles", [])
        data["roles"] = [r["role"] if r.get("role") else r["id"] for r in roles]
        resp, status_code = make_request("patch", api_url, request, data)
        if status_code == 200:
            serializer = self.get_serializer(
                instance, data=data, context=context, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            u_instance = serializer.save()
            assert isinstance(resp, dict)
            resp["user_id"] = u_instance.id
        return Response(data=resp, status=status_code)


class MeView(RetrieveUpdateAPIView):
    """View to serialize the logged in user's data."""

    permission_classes = (IsAuthenticated,)
    search_fields: Sequence[str] = []  # not needed

    queryset: Optional[QuerySet] = None
    serializer_class = UserSerializer

    request: AuthenticatedRequest

    def get_object(self) -> SILUser:
        """Limit this view to work only on the logged in user."""
        return self.request.user


class RoleListCreateView(APIView):
    """Proxy view for auth server roles."""

    permission_classes = (IsAuthenticated,)
    search_fields: Sequence[str] = []  # not needed

    def get(self, request: AuthenticatedRequest) -> Response:
        """Get a list of all the roles from auth server."""
        url = auth_server.ROLES
        resp, status_code = make_request("get", url, request)
        return Response(data=resp, status=status_code)

    def post(
        self, request: AuthenticatedRequest, *args: Any, **kwargs: Any
    ) -> Response:
        """Create roles on auth server."""
        api_url = auth_server.ROLE_PERMS_SPECIAL
        data = copy.deepcopy(request.data)
        templates = data.pop("templates", [])
        all_perms_template = extra_perms_from_name(templates)
        all_perms_template = list(set(all_perms_template))
        data["permission_names"] = all_perms_template
        resp, status_code = make_request("post", api_url, request, data)
        return Response(data=resp, status=status_code)


class RoleRetrieveUpdateView(APIView):
    """Retrieve and update single roles on auth server."""

    permission_classes = (IsAuthenticated,)
    search_fields: Sequence[str] = []  # not needed

    def get(
        self,
        request: AuthenticatedRequest,
        pk: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Get an individual role from auth server."""
        url = auth_server.ROLES + pk + "/"
        resp, status_code = make_request("get", url, request)
        return Response(data=resp, status=status_code)

    def patch(
        self,
        request: AuthenticatedRequest,
        pk: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Update an individual role on auth server."""
        api_url = auth_server.ROLE_PERMS_SPECIAL + pk + "/"
        data = request.data
        resp, status_code = make_request("patch", api_url, request, data)
        return Response(data=resp, status=status_code)

    def delete(
        self,
        request: AuthenticatedRequest,
        pk: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Remove an individual role from auth server."""
        url = auth_server.ROLE_PERMS_SPECIAL + pk + "/"
        resp, status_codes = make_request("delete", url, request)
        return Response(data=resp, status=status_codes)


class RolePermissionsListCreateView(APIView):
    """Auth server role-permissions list view."""

    permission_classes = (IsAuthenticated,)
    search_fields: Sequence[str] = []  # not needed

    def get(self, request: AuthenticatedRequest) -> Response:
        """Get a list of all role permissions."""
        url = auth_server.ROLE_PERMISSIONS
        resp, status_code = make_request("get", url, request)
        return Response(data=resp, status=status_code)

    def post(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Update role permissions on auth server."""
        data = request.data
        api_url = auth_server.ROLE_PERMISSIONS
        resp, status_code = make_request("post", api_url, request, data)
        return Response(data=resp, status=status_code)


class RolePermissionRetrieveUpdateView(APIView):
    """Auth server role permissions detail view."""

    permission_classes = (IsAuthenticated,)
    search_fields: Sequence[str] = []  # not needed

    def get(
        self,
        request: AuthenticatedRequest,
        pk: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Retrieve a single role-permission from auth server."""
        url = auth_server.ROLE_PERMISSIONS + pk + "/"
        resp, status_code = make_request("get", url, request)
        return Response(data=resp, status=status_code)

    def patch(
        self,
        request: AuthenticatedRequest,
        pk: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Update a single role permission on auth server."""
        api_url = auth_server.ROLE_PERMISSIONS + pk + "/"
        data = request.data
        resp, status_code = make_request("patch", api_url, request, data)
        return Response(data=resp, status=status_code)

    def delete(
        self,
        request: AuthenticatedRequest,
        pk: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Remove a single role permission from auth server."""
        url = auth_server.ROLE_PERMISSIONS + pk + "/"
        resp, status_codes = make_request("delete", url, request)
        return Response(data=resp, status=status_codes)


class PermissionListView(APIView):
    """Auth server permissions list view."""

    permission_classes = (IsAuthenticated,)
    search_fields: Sequence[str] = []  # not needed

    def get(self, request: AuthenticatedRequest) -> Response:
        """Get a list of all the permissions from auth server."""
        url = auth_server.PERMISSIONS
        page_size = page_size_auth_server(request.query_params)
        resp, status_code = make_request(
            "get",
            url,
            request,
            custom_params=page_size,
        )

        return Response(data=resp, status=status_code)


class UserMFAViewSet(BaseView):
    """SILUserMFA view set."""

    queryset = SILUserMFA.objects.all()
    serializer_class = UserMFASerializer
    filterset_class = filters.UserMFAFilter
    filter_backends = [
        DjangoFilterBackend,
    ]
    permission_classes = (IsAuthenticated,)

    _data_partition_field = "organisation"

    @action(
        detail=True,
        methods=["POST"],
    )
    def send_otp(self, request: AuthenticatedRequest, pk: uuid.UUID) -> Response:
        """Sends a user an OTP message to their phone."""
        mfa_obj = self.get_object()

        user = request.user
        person = mfa_obj.user.person

        data = {
            "person": person,
            "code": generate_otp(),
            "organisation": person.organisation,
            "branch_id": person.branch_id,
            "created_by": user.id,
            "updated_by": user.id,
        }
        otp_obj = PersonOTP.objects.create(**data)

        mfa_obj.otp = otp_obj
        mfa_obj.save()

        message = (
            f"Hi {person.first_name}, your login verification code is "
            f"{otp_obj.code}. Never share this code."
        )

        send_sms.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
            args=(
                "PATIENT_REGISTRATION",
                message,
                [person.phone_number],
                person.organisation.slade_code,
                person.branch_id,
                person.workstation_id,
            ),
        )

        serializer = self.get_serializer(mfa_obj)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["POST"],
    )
    def verify_otp(self, request: AuthenticatedRequest, pk: uuid.UUID) -> Response:
        """Verify the provided user mfa."""
        serializer = OTPVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.data["code"]

        mfa_obj = self.get_object()

        try:
            mfa_obj.verify_otp_code(code)
        except ModelValidationError as e:
            raise ValidationError(e.messages)

        if mfa_obj.status == MFAStatus.PENDING:
            mfa_obj.status = MFAStatus.ENABLED
            mfa_obj.save()

        return Response(
            {"status": OTPVerificationStatus.VERIFIED}, status=status.HTTP_200_OK
        )
