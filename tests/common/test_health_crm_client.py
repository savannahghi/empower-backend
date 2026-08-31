"""Test chargemaster client instantiaon."""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from sil_healthcrm_client import HealthCRM

from sil_advantage.common.api_clients.health_crm import get_health_crm_client

MOCK_ROOT = "sil_advantage.common.api_clients.health_crm."


@override_settings(
    AUTH_SERVER_API_CONNECTION={
        "HOST": "authserver.advantage.slade360.co.ke/",
        "SCHEME": "https",
        "KEY": "i-am-client-ID",
        "SECRET": "hakunaga-siri-ya-watu-wawili",
        "USER_EMAIL": "advantage_test@slade360.co.ke",
        "USER_PASSWORD": "Some=SecurePassword!",
        "TOKEN_URL": "https://authserver.advantage.slade360.co.ke/",
    },
    HEALTH_CRM_API_URL="crm.slade360.co.ke/api",
)
class TestHealthCRMAPIClientUtilities(TestCase):
    """Tes suite for health crm api client."""

    @patch(MOCK_ROOT + "HealthCRM")
    def test_get_health_crm_client(self, mock_health_crm_class):
        """Test the instantiation of the health crm client."""
        mock_healthcrm_instance = MagicMock(spec=HealthCRM)
        mock_health_crm_class.return_value = mock_healthcrm_instance

        result = get_health_crm_client()
        expected_results = {
            "api_scheme": "https",
            "api_host": "crm.slade360.co.ke/api",
            "oauth_client_id": "i-am-client-ID",
            "oauth_client_secret": "hakunaga-siri-ya-watu-wawili",
            "user_email": "advantage_test@slade360.co.ke",
            "user_password": "Some=SecurePassword!",
            "token_url": "https://authserver.advantage.slade360.co.ke/",
        }

        mock_health_crm_class.assert_called_once_with(**expected_results)

        self.assertEqual(result, mock_healthcrm_instance)
