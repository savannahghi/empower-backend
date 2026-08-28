"""Auth server business partner registry view."""
from typing import Any, Sequence

from rest_framework import response, views
from rest_framework.permissions import IsAuthenticated

from sil_advantage.common.api_clients import auth_server, make_request
from sil_advantage.common.types import AuthenticatedRequest


class BPRegistryView(views.APIView):
    """Proxy view for auth server business partners."""

    permission_classes = (IsAuthenticated,)
    # `search_fields` not required for this proxy view to auth server
    search_fields: Sequence[str] = []
    filter_backends: Sequence[str] = []

    def get(
        self, request: AuthenticatedRequest, *args: Any, **kwargs: Any
    ) -> response.Response:
        """Read business partners from auth server."""
        api_url = auth_server.BP_REGISTRY
        resp, status_code = make_request("get", api_url, request)
        return response.Response(data=resp, status=status_code)
