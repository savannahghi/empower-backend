"""E2E tests for authentication."""

import os
from typing import Any, Optional
from uuid import UUID

import requests

# from django.conf import settings
from behave import given, then
from django.conf import settings
from sil_edge_connection import ApiConnection
from sil_erp_client import ERP


def get_erp_client(workstation_id: Optional[UUID]) -> ERP:
    """Get ERP client and set the necessary headers."""
    config = {**settings.ERP_API_CONFIG}
    erp = ERP(**config)
    erp.conn.base_headers["X-Workstation"] = str(workstation_id)
    erp.conn.base_headers["User-Agent"] = settings.API_USER_AGENT
    return erp


def get_auth_server_credentials(auth_config: Optional[dict] = None) -> dict:
    """Get Auth server credentials."""
    auth_config = auth_config or {
        "HOST": os.getenv(
            "TEST_AUTH_SERVER_API_HOST",
            "authserver.healthcloud.co.ke",
        ),
        "KEY": os.getenv("TEST_AUTHSERVER_API_CLIENT_ID"),
        "SECRET": os.getenv("TEST_AUTHSERVER_CLIENT_SECRET"),
        "USER_EMAIL": os.getenv("TEST_USER_EMAIL_OREGON"),
        "USER_PASSWORD": os.getenv("TEST_USER_PASSWORD_OREGON"),
        "TOKEN_URL": os.getenv(
            "TEST_AUTH_SERVER_API_TOKEN_URL",
            "https://accounts.multitenant.slade360.co.ke/oauth2/token/",
        ),
    }
    return ApiConnection(
        auth_config["HOST"],
        auth_config["KEY"],
        auth_config["SECRET"],
        auth_config["USER_EMAIL"],
        auth_config["USER_PASSWORD"],
        token_url=auth_config["TOKEN_URL"],
    ).credentials


@given("An active user sends login request with correct credentials")
def active_user_logs_in_with_correct_credentials(context: Any) -> None:
    """Test if user gets authenticated if he/she uses correct credentials."""
    context.credz = get_auth_server_credentials()

    assert context.credz["access_token"] is not None


@then("The user should get a key in the response")
def user_gets_key_in_response_and_has_workstation(context: Any) -> None:
    """Test if user gets gets token and has workstation after being authenticated."""
    context.auth_key = context.credz["access_token"]
    header = {"Authorization": f"Bearer {context.auth_key}"}

    WORKSTATION_ENDPOINT = "https://api.erp.release.slade360edi.com/me/?format=json"
    context.workstation = requests.get(WORKSTATION_ENDPOINT, headers=header)

    assert context.workstation.status_code == 200
    assert context.workstation.json()["user_workstations"] is not None
    context.workstation_id = context.workstation.json()["user_workstations"][0][
        "workstation"
    ]
    assert context.workstation_id is not None
