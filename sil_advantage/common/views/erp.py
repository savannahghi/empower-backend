"""ERP proxy view."""
from typing import Any, Sequence

from django.conf import settings
from django.http import FileResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework.status import HTTP_200_OK, HTTP_501_NOT_IMPLEMENTED

from sil_advantage.common.api_clients import make_request
from sil_advantage.common.api_clients.erp import erp_configured
from sil_advantage.common.types import AuthenticatedRequest


class ERPView(APIView):
    """View that proxies to ERP APIs.

    Inspired by ERP's `ChargeMasterView`.
    """

    permission_classes = (IsAuthenticated,)
    filter_backends: Sequence[str] = []
    search_fields: Sequence[str] = []

    def _call(
        self,
        request: AuthenticatedRequest,
        method: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response | FileResponse:
        """Proxy calls to the ERP."""
        if not erp_configured():
            # The ERP is a separate deployment. Reads report an empty collection
            # so the UI still renders; writes say so rather than appearing to
            # succeed while changing nothing.
            if method.lower() != "get":
                return Response(
                    data={
                        "detail": (
                            "This action needs an ERP, which is not configured "
                            "for this deployment."
                        )
                    },
                    status=HTTP_501_NOT_IMPLEMENTED,
                )

            return Response(
                data={"count": 0, "next": None, "previous": None, "results": []},
                status=HTTP_200_OK,
            )

        api_scheme = settings.ERP_API_CONFIG["api_scheme"]
        api_host = settings.ERP_API_CONFIG["api_host"]
        host = f"{api_scheme}://{api_host}"

        url = "{}/{}".format(host, kwargs.get("resource"))
        extra_headers = {
            "X-Workstation": (
                request.META.get("HTTP_X_WORKSTATION")
                or request.META.get("X-Workstation")
            ),
            "HTTP_ORIGIN": request.META.get("HTTP_ORIGIN"),
            "X-Variant": request.META.get("HTTP_X_VARIANT", None)
            or request.META.get("X-Variant", None),
            "Referer": request.META.get("HTTP_REFERER", None)
            or request.META.get("Referer", None),
        }
        extras = {
            "extra_headers": extra_headers,
        }
        if method in ("POST", "PATCH", "PUT"):
            extras["payload"] = request.data.copy()

        response, status_code = make_request(
            method,
            url,
            request,
            **extras,
        )

        if type(response) is FileResponse:
            return response

        return Response(data=response, status=status_code)

    def get(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response | FileResponse:
        """Handle a GET call to the ERP."""
        return self._call(request, "GET", *args, **kwargs)

    def post(
        self, request: AuthenticatedRequest, *args: Any, **kwargs: Any
    ) -> Response | FileResponse:
        """Handle a POST call to the ERP."""
        return self._call(request, "POST", *args, **kwargs)

    def put(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response | FileResponse:
        """Handle a PUT call to the ERP."""
        return self._call(request, "PUT", *args, **kwargs)

    def patch(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response | FileResponse:
        """Handle a PATCH call to the ERP."""
        return self._call(request, "PATCH", *args, **kwargs)

    def delete(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response | FileResponse:
        """Handle a DELETE call to the ERP."""
        return self._call(request, "DELETE", *args, **kwargs)
