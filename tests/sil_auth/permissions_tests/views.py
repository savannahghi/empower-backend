"""Views for permissions tests."""
from rest_framework.response import Response
from rest_framework.views import APIView

from sil_advantage.sil_auth.permission_classes import (
    IsNetworkAdmin,
    OrganisationIsActive,
)


class BaseView(APIView):
    """Base API view."""

    permission_classes = (OrganisationIsActive,)

    def get(self, request, *args, **kwargs):
        """Retrieve resource."""
        return Response()


class TestOrgListView(BaseView):
    """List view for normal user."""

    permissions = {
        "GET": [("list_organisation",)],
        "POST": [("create_organisation",)],
    }


class TestListView(BaseView):
    """List view for network admin."""

    permission_classes = (IsNetworkAdmin,)
    permissions = {
        "GET": [("list_organisation",)],
        "POST": [("create_organisation",)],
    }


class NoPermsListView(BaseView):
    """View without permissions."""

    pass
