"""Unit and integration test fixtures."""
import uuid
from datetime import timedelta
from functools import partial
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils import timezone
from model_bakery import baker
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from sil_advantage.common.models import Person, UserProfile
from sil_advantage.notifications.sms.models import SenderID
from tests.common.test_common_views import global_organisation
from tests.common.utility import patch_baker

pytestmark = pytest.mark.django_db


@pytest.fixture()
def organisation(db):
    """Create and return an organisation."""
    organisation = global_organisation()

    # automatically set the "organisation" when model_bakery is called
    patch_organisation = partial(patch_baker, values={"organisation": organisation})
    org_patcher = patch_organisation()
    org_patcher.start()

    yield organisation  # cleanup occurs after this `yield`
    org_patcher.stop()  # ensure that the org patcher is stopped


@pytest.fixture()
def organisation_user(organisation, client):
    """Return user instance for testing."""
    user = get_user_model().objects.create_superuser(
        email="mail@mail.com", password="pass123", guid=uuid.uuid4()
    )
    global_person = baker.make(
        Person, organisation=organisation, first_name="John", last_name="Doe"
    )
    baker.make(UserProfile, user=user, person=global_person, organisation=organisation)
    return user


@pytest.fixture()
def logged_in_client(organisation_user, client):
    """Return a logged in Django test client."""
    assert client.login(username="mail@mail.com", password="pass123") is True
    return client


@pytest.fixture()
def authenticated_request(rf, organisation_user):
    """Create a request that is authenticated to the organisation user."""
    request = rf.post("/")
    SessionMiddleware().process_request(request)
    request.session.save()
    request.user = organisation_user
    return request


@pytest.fixture()
def drf_authentication_token(organisation_user):
    """Create a DRF authentication token for the organisation user.

    This is used in tests to authenticate calls to the GraphQL endpoint.
    """
    token = Token.objects.create(user=organisation_user)
    return token.key


@pytest.fixture()
def user(organisation):
    """User."""
    user = get_user_model().objects.create_superuser(
        email=settings.SYSTEM_ADMIN_EMAIL, password="password", guid=uuid.uuid4()
    )
    person = baker.make(
        Person, organisation=organisation, first_name="21", last_name="Savage"
    )
    baker.make(UserProfile, user=user, person=person, organisation=organisation)
    return user


@pytest.fixture()
def extra_headers():
    """Extra request headers."""
    return {}


@pytest.fixture()
def client(user, extra_headers):
    """Log in test user and return the client."""
    client = APIClient()
    client.get = partial(client.get, **extra_headers)
    client.patch = partial(client.patch, **extra_headers)
    client.post = partial(client.post, **extra_headers)
    client.login(email=settings.SYSTEM_ADMIN_EMAIL, password="password")
    return client


@pytest.fixture()
def default_transactional_sender(organisation):
    """Default transactional sender id."""
    baker.make(
        SenderID,
        organisation=organisation,
        name="BeWellApp",
        sender_type="TRANSACTION",
        start_date=timezone.now(),
        end_date=timezone.now() + timedelta(days=90),
        active=True,
    )


@pytest.fixture()
def default_promotional_sender(organisation):
    """Default promotional sender id."""
    baker.make(
        SenderID,
        organisation=organisation,
        name="Slade360Adv",
        sender_type="PROMOTION",
        start_date=timezone.now(),
        end_date=timezone.now() + timedelta(days=90),
        active=True,
    )


@pytest.fixture(autouse=True, scope="function")
def mock_provider_is():
    """Mock IS client."""
    mock_is_client = MagicMock()
    with patch(
        "sil_advantage.common.api_clients.is_client.IS", return_value=mock_is_client
    ):
        yield mock_is_client
