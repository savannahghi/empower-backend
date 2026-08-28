"""Test chargemaster client instantiaon."""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from sil_shlink import ShlinkClient

from sil_advantage.common.api_clients.shlink import get_shlink_client

MOCK_ROOT = "sil_advantage.common.api_clients.shlink."


@override_settings(
    SIL_SHLINK={
        "SHLINK_SERVER_URL": "https://foo.com",
        "SHLINK_API_KEY": "bar",
        "SHLINK_CUSTOM_DOMAINs": "e.slade.com",
    }
)
class TestShlinkAPIClientUtilities(TestCase):
    """Tes suite for charge master api client."""

    @patch(MOCK_ROOT + "ShlinkClient")
    def test_get_shlink_client(self, mock_shlink_client):
        """Test the instantiation of the charge master client."""
        mock_shlink_instance = MagicMock(spec=ShlinkClient)
        mock_shlink_client.return_value = mock_shlink_instance

        result = get_shlink_client()

        assertions = {
            "base_url": "https://foo.com",
            "api_key": "bar",
        }

        mock_shlink_client.assert_called_once_with(**assertions)

        self.assertEqual(result, mock_shlink_instance)
