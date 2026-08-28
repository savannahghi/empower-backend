"""Test chargemaster client instantiaon."""
from unittest.mock import MagicMock, patch

from charge_master_client import ChargeMaster
from django.test import TestCase, override_settings

from sil_advantage.common.api_clients.chargemaster import (
    get_chargemaster_client,
)

MOCK_ROOT = "sil_advantage.common.api_clients.chargemaster."


@override_settings(
    CHARGE_MASTER={
        "host": "chargemaster.slade360.co.ke/api",
        "scheme": "https",
        "client_id": "i-am-client-ID",
        "client_secret": "hakunaga-siri-ya-watu-wawili",
        "username": "advantage_test@slade360.co.ke",
        "password": "Some=SecurePassword!",
        "token_url": "https://authserver.advantage.slade360.co.ke/",
        "grant_type": "password",
    }
)
class TestChargeMasterAPIClientUtilities(TestCase):
    """Tes suite for charge master api client."""

    @patch(MOCK_ROOT + "ChargeMaster")
    def test_get_chargemaster_client(self, mock_charge_master_class):
        """Test the instantiation of the charge master client."""
        mock_chargemaster_instance = MagicMock(spec=ChargeMaster)
        mock_charge_master_class.return_value = mock_chargemaster_instance

        result = get_chargemaster_client()

        mock_charge_master_class.assert_called_once_with(
            {
                "scheme": "https",
                "host": "chargemaster.slade360.co.ke/api",
                "oauth_id": "i-am-client-ID",
                "oauth_secret": "hakunaga-siri-ya-watu-wawili",
                "user_email": "advantage_test@slade360.co.ke",
                "user_password": "Some=SecurePassword!",
                "token_url": "https://authserver.advantage.slade360.co.ke/",
            }
        )

        self.assertEqual(result, mock_chargemaster_instance)
