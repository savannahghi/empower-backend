"""Test sil_is client instantiation."""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from sil_is_client import IS

from sil_advantage.common.api_clients.is_client import get_is_client

MOCK_ROOT = "sil_advantage.common.api_clients.is_client."


@override_settings(
    IS_CLIENT={
        "host": "is-api.multitenant.slade360.co.ke/v1",
        "scheme": "https",
        "client_id": "i-am-client-ID",
        "client_secret": "siri-yangu",
        "username": "advantage_test@slade360.co.ke",
        "password": "Some=SecurePassword!",
        "token_url": "https://authserver.advantage.slade360.co.ke/",
    }
)
class TestISAPIClientUtilities(TestCase):
    """Tes suite for sil is api client."""

    @patch(MOCK_ROOT + "IS")
    def test_get_is_client(self, mock_sil_is_class):
        """Test the instantiation of the is client."""
        mock_is_instance = MagicMock(spec=IS)
        mock_sil_is_class.return_value = mock_is_instance

        result = get_is_client()

        mock_sil_is_class.assert_called_once_with(
            {
                "scheme": "https",
                "host": "is-api.multitenant.slade360.co.ke/v1",
                "oauth_id": "i-am-client-ID",
                "oauth_secret": "siri-yangu",
                "user_email": "advantage_test@slade360.co.ke",
                "user_password": "Some=SecurePassword!",
                "token_url": "https://authserver.advantage.slade360.co.ke/",
            }
        )

        self.assertEqual(result, mock_is_instance)
