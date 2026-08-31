"""Test tariff client."""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from sil_advantage.common.api_clients.tariff_client import (
    get_access_token,
    get_route_data,
)


@override_settings(
    TARRIFS_AUTH_SERVER_LOGIN_CONFIG={
        "HOST": "https://accounts.edi.slade360.co.ke",
        "KEY": "tariff-key",
        "SECRET": "tariff-secret-key",
        "USER_EMAIL": "tariff-client-email",
        "USER_PASSWORD": "tariff-password",
        "TOKEN_URL": "https://accounts.edi.slade360.co.ke/oauth2/token/",
    },
    TARIFF_BASE_URL="https://api.tariffs.savannahghi.org",
)
class TestTariffClient(TestCase):
    """Test suite for tariff api client."""

    @patch("sil_advantage.common.api_clients.tariff_client.get_auth_server_credentials")
    def test_get_access_token(self, mock_access_token):
        """Test getting access token from auth server."""
        mock_access_token.return_value = {
            "access_token": "mocked-access-token",
        }
        access_token = get_access_token()
        self.assertEqual(access_token, "mocked-access-token")
        mock_access_token.assert_called_once()

    @patch("sil_advantage.common.api_clients.tariff_client.get_access_token")
    @patch("sil_advantage.common.api_clients.tariff_client.requests.get")
    def test_get_route_of_administration_data(
        self, mock_fetch_route_data, mock_get_access_token
    ):
        """Test fetch route of administration data."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"synonym": "IV", "name": "Intravenous"},
                {"synonym": "PO", "name": "Oral"},
                {"synonym": "IM", "name": "Intramuscular"},
            ]
        }
        mock_fetch_route_data.return_value = mock_response
        mock_get_access_token.return_value = "mock-access-token"
        expected_response = {
            "IV": "Intravenous",
            "PO": "Oral",
            "IM": "Intramuscular",
        }
        route_data = get_route_data()
        self.assertEqual(expected_response, route_data)

        mock_get_access_token.assert_called_once()
        mock_fetch_route_data.assert_called_once_with(
            "https://api.tariffs.savannahghi.org/v1/catalog/routes/",
            headers={"Authorization": "Bearer mock-access-token"},
        )

    @patch("sil_advantage.common.api_clients.tariff_client.get_access_token")
    @patch("sil_advantage.common.api_clients.tariff_client.requests.get")
    def test_get_route_of_administration_data_with_no_data(
        self, mock_fetch_route_data, mock_get_access_token
    ):
        """Test fetch route of administration data."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_fetch_route_data.return_value = mock_response
        mock_get_access_token.return_value = "mock-access-token"
        expected_response = {}
        route_data = get_route_data()
        self.assertEqual(expected_response, route_data)

        mock_get_access_token.assert_called_once()
        mock_fetch_route_data.assert_called_once_with(
            "https://api.tariffs.savannahghi.org/v1/catalog/routes/",
            headers={"Authorization": "Bearer mock-access-token"},
        )
