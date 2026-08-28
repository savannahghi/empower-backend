"""Settings views."""
from typing import Any, Sequence, cast

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList
from rest_framework.views import APIView

from sil_advantage.common.types import AuthenticatedRequest
from sil_advantage.settings import models, serializers


class OrganisationSettingsView(APIView):
    """Organisation settings."""

    permission_classes = (IsAuthenticated,)
    filter_backends: Sequence[str] = []
    search_fields: Sequence[str] = []

    def _serialize_all_org_settings(
        self, organisation: models.Organisation
    ) -> ReturnDict | ReturnList:
        """Serialize all organisation settings."""
        settings = models.OrganisationSetting.all_org_settings(organisation)
        return serializers.OrganisationSettingSerializer(
            settings,
            many=True,
        ).data

    def get(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Retrieve all organisation settings."""
        org = request.user.organisation
        data = self._serialize_all_org_settings(org)
        return Response(data=data, status=HTTP_200_OK)

    def patch(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Update a list of organisation settings.

        Expected payload is a list of settings (`id` is optional):
        [
            {
                "id": "379155e1-f469-459d-ab63-f16aa8708733",
                "name": "patients:patient_id_format",
                "value": "MIRAZI/{file_number:04d}/{created:%y}"
            }
        ]
        """
        org = request.user.organisation
        for setting in cast(list, request.data):
            models.OrganisationSetting.set_org_setting(
                org,
                setting["name"],
                setting["value"],
            )

        data = self._serialize_all_org_settings(org)
        return Response(data=data, status=HTTP_200_OK)


class BranchSettingsView(APIView):
    """Branch settings."""

    def _serialize_all_branch_settings(
        self, organisation: models.Organisation, branch_id: Any | None
    ) -> ReturnDict | ReturnList:
        """Serialize all branch settings."""
        settings = models.OrganisationSetting.all_branch_settings(
            organisation, branch_id
        )
        return serializers.OrganisationSettingSerializer(
            settings,
            many=True,
        ).data

    def get(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Retrieve all branch settings."""
        branch_id = request.META.get("HTTP_X_BRANCH") or request.META.get("X-Branch")
        org = request.user.organisation
        data = self._serialize_all_branch_settings(
            org,
            branch_id,
        )
        return Response(data=data, status=HTTP_200_OK)

    def patch(
        self,
        request: AuthenticatedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """Update a list of branch settings."""
        org = request.user.organisation
        branch_id = request.META.get("HTTP_X_BRANCH") or request.META.get("X-Branch")
        for setting in cast(list, request.data):
            models.OrganisationSetting.set_branch_setting(
                org,
                branch_id,
                setting["name"],
                setting["value"],
            )

        data = self._serialize_all_branch_settings(
            org,
            branch_id,
        )
        return Response(data=data, status=HTTP_200_OK)
