"""api client to fetch drug information from tarrifs and terminologies."""
import requests
from django.conf import settings

from sil_advantage.common.api_clients.auth_server import (
    get_auth_server_credentials,
)


def get_access_token() -> str:
    """Fetch route of administration choices."""
    config = {
        "HOST": settings.TARRIFS_AUTH_SERVER_LOGIN_CONFIG["HOST"],
        "KEY": settings.TARRIFS_AUTH_SERVER_LOGIN_CONFIG["KEY"],
        "SECRET": settings.TARRIFS_AUTH_SERVER_LOGIN_CONFIG["SECRET"],
        "USER_EMAIL": settings.TARRIFS_AUTH_SERVER_LOGIN_CONFIG["USER_EMAIL"],
        "USER_PASSWORD": settings.TARRIFS_AUTH_SERVER_LOGIN_CONFIG["USER_PASSWORD"],
        "TOKEN_URL": settings.TARRIFS_AUTH_SERVER_LOGIN_CONFIG["TOKEN_URL"],
    }
    response = get_auth_server_credentials(auth_config=config)
    return response["access_token"]


def get_route_data() -> dict:
    """Fetching route data from tariff."""
    access_token = get_access_token()
    fetch_routes_url = f"{settings.TARIFF_BASE_URL}/v1/catalog/routes/"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(fetch_routes_url, headers=headers)  # type: ignore
    returned_payload = response.json()
    mapped_data = {}
    if returned_payload["results"]:
        for route in returned_payload["results"]:
            mapped_data[route["synonym"]] = route["name"]
    return mapped_data
