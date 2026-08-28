"""Shared auth server URLs."""
from functools import partial
from typing import Optional

from django.conf import settings
from sil_edge_connection.connection import ApiConnection

from sil_advantage.common.cache import cached


@cached(ttl=45 * 60)
def get_auth_server_credentials(auth_config: Optional[dict] = None) -> dict:
    """Get Auth server credentials."""
    auth_config = auth_config or settings.AUTH_SERVER_API_CONNECTION
    return ApiConnection(
        auth_config["HOST"],
        auth_config["KEY"],
        auth_config["SECRET"],
        auth_config["USER_EMAIL"],
        auth_config["USER_PASSWORD"],
        token_url=auth_config["TOKEN_URL"],
    ).credentials


def get_auth_server_api_connection() -> ApiConnection:
    """Get Auth server credentials."""
    auth_config = settings.AUTH_SERVER_API_CONNECTION
    return ApiConnection(
        auth_config["HOST"],
        auth_config["KEY"],
        auth_config["SECRET"],
        auth_config["USER_EMAIL"],
        auth_config["USER_PASSWORD"],
        token_url=auth_config["TOKEN_URL"],
    )


def create_url(base_url: str, path: str) -> str:
    """Create a fully qualified URL by combining the base_url and path."""
    return base_url + path


url = settings.SIL_AUTH_SERVER_DOMAIN
new_url = partial(create_url, url)

ROLE_PERMS_SPECIAL = new_url("/v1/role/role_special/")
ROLE_PERMISSIONS = new_url("/v1/role/role_permissions/")
PERMISSIONS = new_url("/v1/role/permissions/")
ROLES = new_url("/v1/role/")
USERS_SPECIAL = new_url("/v1/user/user_roles/")
BP_REGISTRY = new_url("/v1/bp/business_partners/")
