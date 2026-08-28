"""common utilities."""
import logging
from datetime import datetime, timezone
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from requests import Timeout, TooManyRedirects, request
from requests.models import Response
from urllib3.exceptions import MaxRetryError

from sil_advantage.common.api_clients.auth_server import (
    get_auth_server_credentials,
)

LOGGER = logging.getLogger(__name__)


class APIConnectionErrorException(Exception):
    """Exception raised for API connection errors."""

    pass


class CubeJS:
    """Class to communicate with Quintus CubeJS deployment."""

    def __init__(self, slade_code: int) -> None:
        """Cube Constructor.

        Args:
            slade_code: A unique code belonging to an Organisation.
        """
        self.headers: dict[str, str] = {"Content-Type": "application/json"}
        self.slade_code = slade_code

        self.base_url = settings.QUINTUS_BACKEND_URL
        self.query_base_url = f"{self.base_url}/cubejs-api/v1/load"

        self.get_access_token()

    def get_access_token(self) -> dict:
        """Generate CubeJS API access token."""
        authserver_token = get_auth_server_credentials()
        authserver_token["expire_at"] = datetime.fromtimestamp(
            authserver_token["token_acquired"] + 3_600, timezone.utc
        ).isoformat()

        user_guid = str(
            get_user_model()
            .objects.get(email=settings.AUTH_SERVER_API_CONNECTION["USER_EMAIL"])
            .guid
        )

        auth_payload = {
            "token": {**authserver_token},
            "user": {
                "guid": str(user_guid),
                "roles": ["Superuser", "Quintus", "Organisation Admin"],
                "business_partner": self.slade_code,
            },
        }

        jwt = self.api_call(
            f"{self.base_url}/api/v1/auth/login", payload=auth_payload
        ).text
        LOGGER.info("Login attempt to CubeJS API successful!")

        headers = {"Authorization": f"Bearer {jwt}"}
        self.headers.update(headers)

        return self.headers

    def api_call(
        self,
        url: str,
        method: str = "POST",
        headers: dict[str, str] | None = None,  # type: ignore
        payload: dict[str, Any] | None = None,  # type: ignore
    ) -> Response:
        """General API call that other methods will use.

        Args:
            url: The API `URL` to hit.
            method: `HTTP` request method. Either `POST` or `GET`.
            headers: `HTTP` headers.
            payload: Holds the payload to send to the API.

        Returns:
            An API response if successful.

        Raises:
            APIConnectionErrorException: If there's an error connecting to Cube.
        """
        headers = headers or {}
        headers.update(self.headers)
        request_kwargs: dict[str, Any] = {"headers": headers}
        request_kwargs["json"] = payload

        try:
            # ignore type error due to dictionary unpacking
            response = request(method, url, **request_kwargs)  # type: ignore
        except (
            ConnectionError,
            TooManyRedirects,
            Timeout,
            MaxRetryError,
        ) as e:
            error_msg = str(e)
            LOGGER.error(error_msg)
            raise APIConnectionErrorException(error_msg)
        return response
