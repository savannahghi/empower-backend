"""Test common cube utils."""
import re
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings

from sil_advantage.common.utilities.cube import (
    APIConnectionErrorException,
    CubeJS,
)
from tests.common.utility import QuintusReponse

MOCK_ROOT = "sil_advantage.common.utilities.cube."

pytestmark = pytest.mark.django_db


@patch.object(CubeJS, "api_call")
@patch(MOCK_ROOT + "get_auth_server_credentials")
@patch("sil_advantage.common.utilities.cube.LOGGER")
def test_get_access_token(mock_logger, mock_auth, mock_api_call, organisation):
    """Test obtaining an access token from Cube."""
    credentials = {
        "access_token": "P8HmBs8fsNIkTL7ikcntaWtyX3stY2",
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": "advantage.appointment.read",
        "refresh_token": "Zzaa0Rzifj63Lo1Lnm2eJXK0rJ2awC",
        "token_acquired": 1686209213.636824,
    }
    mock_auth.return_value = credentials

    get_user_model().objects.create_superuser(
        email=settings.AUTH_SERVER_API_CONNECTION["USER_EMAIL"],
        password="pass123",
        guid="5006ae91-d8b6-4e99-9ea9-9ddb462f4721",
        permissions="",
    )

    quintus_response = QuintusReponse()
    mock_api_call.side_effect = quintus_response.mocked_login

    CubeJS(organisation.slade_code)
    mock_logger.info.assert_called_once_with("Login attempt to CubeJS API successful!")


@override_settings(QUINTUS_BACKEND_URL="https://analytics.quintas.com")
@patch("sil_advantage.common.utilities.cube.LOGGER")
@patch.object(CubeJS, "get_access_token")
@patch(MOCK_ROOT + "request")
def test_cube_api_call(mock_request, mock_cube_login, mock_logger, organisation):
    """Test making API call to Cube."""
    cube_js = CubeJS(organisation.slade_code)
    cube_query = {
        "dimensions": ["patients_poc.patient_id"],
        "filters": [
            {
                "or": [
                    {
                        "and": [
                            {
                                "member": "patients_poc.age",
                                "operator": "gt",
                                "values": ["45"],
                            }
                        ]
                    },
                ]
            }
        ],
        "total": True,
    }

    def mocked_cube_response(url, *args, **kwargs):
        """Mock query response from Cube."""
        data = [
            {"patients_poc.patient_id": "abf685c2-9cc5-4d17-aa81-9944a0f590fa"},
        ]

        return QuintusReponse(data={"data": data})

    mock_request.side_effect = mocked_cube_response
    cube_js.api_call(url=cube_js.query_base_url, payload=cube_query).json()

    mock_request.assert_called_with(
        "POST",
        cube_js.query_base_url,
        headers={"Content-Type": "application/json"},
        json=cube_query,
    )

    # test api call with connection faliure
    mock_request.reset_mock(side_effect=True)
    error_msg = (
        "HTTPConnectionPool(host='analytics.example.com', "
        "port=443): Max retries exceeded with url: "
        "/sms/callbacks/ (Caused by NewConnectionError("
        "'<urllib3.connection.HTTPConnection object at 0x7f6884ae21a0>: "
        "Failed to establish a new connection: [Errno 111] Connection refused'))"
    )
    mock_request.side_effect = ConnectionError(error_msg)

    with pytest.raises(APIConnectionErrorException, match=re.escape(error_msg)):
        cube_js.api_call(url=cube_js.query_base_url, payload=cube_query).json()
        mock_logger.error.assert_called_once_with(error_msg)
