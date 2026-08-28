"""E2E tests for organisation and branch settings using requests."""

import json

import requests
from behave import given, then, when

from features.steps.authentication.login_logout import (
    get_auth_server_credentials,
)

BASE_URL = "https://api.advantage.release.slade360edi.com/api/settings"


@given("I am an authenticated user")
def authenticate_user(context):
    """Authenticate a user."""
    context.credz = get_auth_server_credentials()

    # Set the authorization headers with other necessary headers
    context.auth_headers = {
        "Authorization": f"Bearer {context.credz['access_token']}",
        "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
        "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
        "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
        "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    }


@when('I send a GET request to "{url}"')
def send_get_request(context, url):
    """Send a GET request to the specified URL."""
    # Construct the full URL
    full_url = f"{BASE_URL}/{url}/"
    # Send a GET request using requests
    context.response = requests.get(full_url, headers=context.auth_headers)


@then("I receive a 200 OK response")
def check_200_response(context):
    """Check that the response status is 200 OK."""
    assert context.response.status_code == 200


@then("I receive {count:d} organisation settings")
def verify_org_settings_count(context, count):
    """Verify the number of organisation settings received."""
    response_data = context.response.json()
    assert (
        len(response_data) == count
    ), f"Expected {count} settings, got {len(response_data)}"


@given('the branch ID is "{branch_id}"')
def set_branch_id(context, branch_id):
    """Store the branch ID in context."""
    context.branch_id = branch_id


@when('I send a GET request to {branch_url} with branch ID "{branch_id}"')
def send_get_request_with_branch(context, branch_url, branch_id):
    """Send a GET request to the branch URL with the given branch ID."""
    # Construct the full URL with the branch ID as a header
    full_url = f"{BASE_URL}/{branch_url}/"
    context.branch_id = branch_id
    # Send a GET request using requests
    headers = {**context.auth_headers, "X-Branch": branch_id}
    context.response = requests.get(full_url, headers=headers)


@then("I receive {count:d} branch settings")
def verify_branch_settings_count(context, count):
    """Verify the number of branch settings received."""
    response_data = context.response.json()
    assert (
        len(response_data) == count
    ), f"Expected {count} settings, got {len(response_data)}"


@when('I send a PATCH request to "{branch_url}" with branch ID and the JSON')
def send_patch_request_with_branch(context, branch_url):
    """Send a PATCH request to the branch URL with branch ID and JSON data."""
    # Load JSON data from the scenario
    data = json.loads(context.text)
    # Construct the full URL
    full_url = f"{BASE_URL}/{branch_url}/"

    # Send a PATCH request using requests
    headers = {**context.auth_headers, "X-Branch": context.branch_id}
    context.response = requests.patch(full_url, json=data, headers=headers)


@then('the branch setting "{name}" is updated to "{value}"')
def verify_branch_setting_updated(context, name, value):
    """Verify that the branch setting is updated with the correct value."""
    setting = next((s for s in context.response.json() if s["name"] == name), None)
    assert setting is not None, f"Setting '{name}' not found in response"
    assert setting["value"][0] == int(
        value
    ), f"Expected value '{int(value)}', got '{setting['value'][0]}'"


@when('I send a PATCH request to "/org_settings/" with the following JSON')
def send_patch_request_org_settings(context):
    """Send a PATCH request to update organisation settings."""
    # Load JSON data from the scenario
    data = json.loads(context.text)

    # Construct the full URL
    full_url = f"{BASE_URL}/org_settings/"

    # Send a PATCH request using requests
    context.response = requests.patch(full_url, json=data, headers=context.auth_headers)


@then('the organisation setting "{name}" is updated to "{value}"')
def verify_org_setting_updated(context, name, value):
    """Verify that the organisation setting is updated with the correct value."""
    setting = next((s for s in context.response.json() if s["name"] == name), None)
    context.setting = setting
    assert setting is not None, f"Setting '{name}' not found in response"
    assert (
        setting["value"] == value
    ), f"Expected value '{value}', got '{setting['value']}'"


@then('the description is "{description}"')
def check_description(context, description):
    """Verify the description of the setting."""
    setting = next(
        (s for s in context.response.json() if s["description"] == description), None
    )
    assert setting["description"] == description


@then('the setting type is "{setting_type}"')
def check_setting_type(context, setting_type):
    """Verify the type of the setting."""
    setting = next(
        (s for s in context.response.json() if s["setting_type"] == setting_type), None
    )
    assert setting["setting_type"] == setting_type
