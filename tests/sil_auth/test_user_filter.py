"""Test user filters."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from nio import AsyncClient
from rest_framework.reverse import reverse

from tests.common.test_common_views import LoggedInMixin
from tests.common.utility import AsyncMagicMock, PicklableMagicMock, patch_baker


class TestWorkstationExclude(LoggedInMixin):
    """Test case for user filters."""

    def setUp(self):
        """Test set up."""
        super().setUp()
        values = {"organisation": self.user.organisation}
        patcher = patch_baker(values=values)
        patcher.start()
        self.addCleanup(patcher.stop)

    @override_settings(MATRIX_SECRET="a-secret")
    @patch.object(AsyncClient, "set_displayname", new_callable=AsyncMagicMock)
    @patch(
        "sil_advantage.notifications.matrix.requests",
        new_callable=PicklableMagicMock,
    )
    def test_user_organisation_filter(
        self,
        mock_matrix_requests,
        mock_set_matrix_display_name,
    ):
        """Test filter user by organisaton."""
        matrix_uid = "@2bdf4e17-cb39-4626-a29d-a80040d67857:slade360edi.com"
        mock_matrix_requests.post.return_value.json.return_value = {
            "user_id": matrix_uid,
            "access_token": "my-access-token",
            "home_server": "slade360edi.com",
            "device_id": "GVROMSUCDE",
            "well_known": {
                "m.homeserver": {
                    "base_url": "https://matrix.slade360.uat.slade360edi.com/"
                }
            },
            "_cache_key": "2d0340b3bfedb72dfcb845e8d32b31b7",
        }

        url = reverse("user-list")
        filter_params = {"organisation": self.user.organisation.pk}
        resp = self.client.get(url, filter_params)
        assert resp.status_code == 200, resp.data
        for result in resp.data["results"]:
            result_pk = result["id"]
            result_obj = get_user_model().objects.get(pk=result_pk)
            assert result_obj.organisation == self.user.organisation
