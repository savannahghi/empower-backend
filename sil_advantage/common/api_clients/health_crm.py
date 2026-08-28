"""HealthCRM Wrapper."""
from django.conf import settings
from sil_edge_connection.connection import ApiConnection
from sil_healthcrm_client import HealthCRM
from sil_wrapper_utils import CRUDMixin

from sil_advantage.common.api_clients.auth_server import (
    get_auth_server_credentials,
)


class HealthCRMClient:
    """HealthCRM Client."""

    class ProfilesAPI(CRUDMixin):
        """HealthCRM Profile Resource."""

        def __init__(
            self,
            connection: ApiConnection,
            base_url: str = "/v1/identities/profiles/",
        ) -> None:
            """Set up Profiles API."""
            self.connection = connection
            self.base_url = base_url

    def __init__(self) -> None:
        """Initialize the HealthCRM Client."""
        auth_config = settings.AUTH_SERVER_API_CONNECTION  # type: ignore
        self.conn = ApiConnection(
            settings.HEALTH_CRM_API_URL,  # type: ignore
            auth_config["KEY"],
            auth_config["SECRET"],
            auth_config["USER_EMAIL"],
            auth_config["USER_PASSWORD"],
            token_url=None,
        )
        credz = get_auth_server_credentials()
        self.conn.base_headers["Authorization"] = f"Bearer {credz['access_token']}"

        # Endpoints
        self.profiles = self.ProfilesAPI(self.conn)


def get_health_crm_client() -> HealthCRM:
    """Gets a health CRM client instance."""
    auth_config = settings.AUTH_SERVER_API_CONNECTION

    config = {
        "api_host": settings.HEALTH_CRM_API_URL,
        "oauth_client_id": auth_config["KEY"],
        "oauth_client_secret": auth_config["SECRET"],
        "user_email": auth_config["USER_EMAIL"],
        "user_password": auth_config["USER_PASSWORD"],
        "token_url": auth_config["TOKEN_URL"],
        "api_scheme": auth_config["SCHEME"],
    }

    return HealthCRM(**config)
