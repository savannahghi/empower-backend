"""User administration backed by Keycloak.

Upstream these screens read and write users on the ERP. Keycloak holds them in
this deployment, so this adapts its admin API to the shape the list and form
components expect: DRF pagination, and `first_name`/`last_name` rather than
Keycloak's camel case.

Every response is scoped to the caller's organisation through the
`business_partner` attribute, so one organisation's administrator cannot see or
change another's staff.
"""
import logging
from math import ceil
from typing import Any, Optional

from django.utils.crypto import get_random_string
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.sil_auth.keycloak import keycloak_admin

LOGGER = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100


def to_representation(user: dict[str, Any]) -> dict[str, Any]:
    """Shape a Keycloak user the way the screens expect."""
    return {
        "id": user["id"],
        # The detail route keys on guid; Keycloak's id is the stable identifier.
        "guid": user["id"],
        "email": user.get("email") or user.get("username") or "",
        "first_name": user.get("firstName") or "",
        "last_name": user.get("lastName") or "",
        "enabled": user.get("enabled", True),
    }


def normalise_roles(value: Any) -> list[str]:
    """Accept role names, or the {id, name} objects the form sends."""
    if not value:
        return []

    if isinstance(value, (str, dict)):
        value = [value]

    names = []
    for role in value:
        if isinstance(role, dict):
            name = role.get("id") or role.get("name")
        else:
            name = role
        if name:
            names.append(str(name))

    return names


def paginated(
    request: Request,
    results: list[dict[str, Any]],
    *,
    total: int,
    page: int,
    size: int,
) -> dict[str, Any]:
    """Shape a page the way SILPagingSerializer does.

    The list components read current_page, total_pages and the indices, not
    just count and results.
    """
    total_pages = max(1, ceil(total / size)) if size else 1
    start = ((page - 1) * size) + 1 if total else 0
    end = min(page * size, total)

    def link(number: Optional[int]) -> Optional[str]:
        if number is None:
            return None

        query = request.query_params.copy()
        query["page"] = number

        return f"{request.build_absolute_uri(request.path)}?{query.urlencode()}"

    return {
        "count": total,
        "next": link(page + 1 if page < total_pages else None),
        "previous": link(page - 1 if page > 1 else None),
        "page_size": size,
        "current_page": page,
        "total_pages": total_pages,
        "start_index": start,
        "end_index": end,
        "results": results,
    }


class UserViewSet(ViewSet):
    """List, create and reset the password of an organisation's users."""

    permission_classes = (IsAuthenticated,)

    def _slade_code(self, request: AuthenticatedRequest) -> int:
        organisation = request.user.organisation

        if organisation is None:
            raise ValidationError({"detail": "No organisation on this account."})

        return int(organisation.slade_code)

    def _page(self, request: Request) -> tuple[int, int]:
        try:
            page = max(int(request.query_params.get("page", 1)), 1)
            size = int(request.query_params.get("page_size", DEFAULT_PAGE_SIZE))
        except ValueError:
            raise ValidationError({"detail": "page and page_size must be numbers."})

        return page, min(max(size, 1), MAX_PAGE_SIZE)

    def list(self, request: AuthenticatedRequest) -> Response:
        """One page of the caller's organisation, DRF shaped."""
        page, size = self._page(request)
        search = request.query_params.get("search") or request.query_params.get(
            "first_name"
        )

        users, total = keycloak_admin().list_users(
            slade_code=self._slade_code(request),
            search=search,
            first=(page - 1) * size,
            max_results=size,
        )

        return Response(
            paginated(
                request,
                [to_representation(user) for user in users],
                total=total,
                page=page,
                size=size,
            )
        )

    def retrieve(self, request: AuthenticatedRequest, pk: str) -> Response:
        admin = keycloak_admin()
        user = admin.get_user(pk)

        if user is None:
            raise NotFound("No such user.")

        attributes = user.get("attributes") or {}
        owner = (attributes.get("business_partner") or [None])[0]

        if owner is not None and int(owner) != self._slade_code(request):
            raise NotFound("No such user.")

        return Response(to_representation(user))

    def create(self, request: AuthenticatedRequest) -> Response:
        """Add a user to the caller's organisation."""
        data = request.data
        # The add-user form posts camel case; other callers use snake case.
        first_name = data.get("first_name") or data.get("firstName") or ""
        last_name = data.get("last_name") or data.get("lastName") or ""
        email = data.get("email") or ""

        missing = {
            name: "This field is required."
            for name, value in (
                ("email", email),
                ("first_name", first_name),
                ("last_name", last_name),
            )
            if not value
        }

        if missing:
            raise ValidationError(missing)

        admin = keycloak_admin()

        if admin.find_user(email):
            raise ValidationError({"email": "A user with this email already exists."})

        admin.ensure_claim_wiring()
        password = get_random_string(12)
        slade_code = self._slade_code(request)

        admin.upsert_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            slade_code=slade_code,
            password=password,
            realm_role="",
        )

        created = admin.find_user(email)
        roles = normalise_roles(data.get("user_roles"))

        if roles:
            admin.set_realm_roles(created["id"], roles)

        body = to_representation(created)
        # No mail is sent from this deployment, so the credential is returned
        # once for the administrator to pass on.
        body["temporary_password"] = password

        return Response(body, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["POST"], url_path="reset_password")
    def reset_password(self, request: AuthenticatedRequest) -> Response:
        """Issue a new password for a user in the caller's organisation."""
        email = request.data.get("email")

        if not email:
            raise ValidationError({"email": "This field is required."})

        admin = keycloak_admin()
        user = admin.find_user(email)

        if user is None:
            raise NotFound("No such user.")

        attributes = user.get("attributes") or {}
        owner = (attributes.get("business_partner") or [None])[0]

        if owner is not None and int(owner) != self._slade_code(request):
            raise NotFound("No such user.")

        password = get_random_string(12)
        admin.set_password(user["id"], password)

        return Response({"email": email, "temporary_password": password})


class RealmRoleView(APIView):
    """List the assignable roles, and assign them to a user.

    The add-user form reads this collection and PATCHes the same URL with
    `{user_id, role_ids}` to save, so both verbs live here.
    """

    permission_classes = (IsAuthenticated,)

    def _owns(self, request: AuthenticatedRequest, user: dict) -> bool:
        attributes = user.get("attributes") or {}
        owner = (attributes.get("business_partner") or [None])[0]
        organisation = request.user.organisation

        if organisation is None:
            return False

        return owner is None or int(owner) == int(organisation.slade_code)

    def get(self, request: AuthenticatedRequest) -> Response:
        roles = keycloak_admin().list_realm_roles()
        results = [{"id": role["name"], "name": role["name"]} for role in roles]

        search = (request.query_params.get("search") or "").lower()

        if search:
            results = [r for r in results if search in r["name"].lower()]

        return Response(
            paginated(
                request, results, total=len(results), page=1, size=len(results) or 1
            )
        )

    def patch(self, request: AuthenticatedRequest) -> Response:
        """Set a user's roles to exactly those given."""
        user_id = request.data.get("user_id")
        role_ids = request.data.get("role_ids") or []

        if not user_id:
            raise ValidationError({"user_id": "This field is required."})

        admin = keycloak_admin()
        user = admin.get_user(str(user_id))

        if user is None or not self._owns(request, user):
            raise NotFound("No such user.")

        admin.set_realm_roles(user["id"], normalise_roles(role_ids))

        return Response(
            {
                "id": user["id"],
                "first_name": user.get("firstName") or "",
                "last_name": user.get("lastName") or "",
                "roles": normalise_roles(role_ids),
            }
        )
