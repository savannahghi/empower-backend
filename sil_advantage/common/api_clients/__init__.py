"""Shared auth server connection attributes module."""
from .api_connection import make_request
from .auth_server import (
    PERMISSIONS,
    ROLE_PERMS_SPECIAL,
    USERS_SPECIAL,
    get_auth_server_api_connection,
    get_auth_server_credentials,
)
from .chargemaster import get_chargemaster_client
from .erp import get_erp_client
from .health_crm import get_health_crm_client

__all__ = [
    "get_auth_server_credentials",
    "get_erp_client",
    "make_request",
    "ROLE_PERMS_SPECIAL",
    "PERMISSIONS",
    "USERS_SPECIAL",
    "get_auth_server_api_connection",
    "get_chargemaster_client",
    "get_health_crm_client",
]
