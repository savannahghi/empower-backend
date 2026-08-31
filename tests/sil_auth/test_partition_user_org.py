"""Tests for user partition by organisationMixin."""
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from model_bakery import baker
from nio import AsyncClient
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from sil_advantage.common.models import Organisation, Person, UserProfile
from sil_advantage.permissions import perms as perms
from tests.common.utility import AsyncMagicMock, PicklableMagicMock

USER_MODEL = get_user_model()
http_origin_header = {"HTTP_ORIGIN": "http://sil_advantage.com"}


@override_settings(MATRIX_SECRET="a-secret")
class PartialOrganisationTest(APITestCase):
    """Test case for user queryset.

    Tests to check that organisation filtering works. A network admin should
    be able to see all users and other users should only be able to see users
    that belong to that organisation.
    """

    @patch.object(AsyncClient, "set_displayname", new_callable=AsyncMagicMock)
    @patch(
        "sil_advantage.notifications.matrix.requests",
        new_callable=PicklableMagicMock,
    )
    def test_network_admin(
        self,
        mock_matrix_requests,
        mock_set_matrix_display_name,
    ):
        """Test network admin can list all users."""
        matrix_uid = "@2bdf4e17-cb39-4626-a29d-a80040d67857:slade360edi.com"
        mock_matrix_requests.post.return_value.json.return_value = {
            "user_id": matrix_uid,
            "access_token": "my-access-token",
            "home_server": "slade360edi.com",
            "device_id": "GVROMSUCDE",
            "well_known": {
                "m.homeserver": {
                    "base_url": "https://matrix.slade360.uat.slade360edi.com/"
                }
            },
            "_cache_key": "2d0340b3bfedb72dfcb845e8d32b31b7",
        }

        user1 = USER_MODEL.objects.create_user(
            email="john@doe.com",
            guid=uuid.uuid4(),
            password="hello_world6",
            permissions=perms.CROSS_NETWORK_ADMIN[0],
        )
        org = baker.make(Organisation)
        org_2 = baker.make(Organisation)
        user2 = USER_MODEL.objects.create_user(
            email="john@doethesecond.com",
            guid=uuid.uuid4(),
            password="hello_world6",
        )
        person1 = Person.objects.create(
            first_name="Test",
            last_name="User",
            organisation=org,
            created_by=user1.pk,
            updated_by=user1.pk,
        )
        person2 = Person.objects.create(
            first_name="Test",
            last_name="User",
            organisation=org_2,
            created_by=user1.pk,
            updated_by=user1.pk,
        )
        UserProfile.objects.create(
            user=user1,
            person=person1,
            organisation=org,
            created_by=user1.pk,
            updated_by=user1.pk,
        )
        UserProfile.objects.create(
            user=user2,
            person=person2,
            organisation=org_2,
            created_by=user1.pk,
            updated_by=user1.pk,
        )

        self.client.login(username="john@doe.com", password="hello_world6")
        url = reverse("user-list")
        response = self.client.get(url)
        assert response.data["count"] == 2

    @patch.object(AsyncClient, "set_displayname", new_callable=AsyncMagicMock)
    @patch(
        "sil_advantage.notifications.matrix.requests",
        new_callable=PicklableMagicMock,
    )
    def test_organisation_admin(
        self,
        mock_matrix_requests,
        mock_set_matrix_display_name,
    ):
        """Test organisation admin list users in the organisation."""
        matrix_uid = "@2bdf4e17-cb39-4626-a29d-a80040d67857:slade360edi.com"
        mock_matrix_requests.post.return_value.json.return_value = {
            "user_id": matrix_uid,
            "access_token": "my-access-token",
            "home_server": "slade360edi.com",
            "device_id": "GVROMSUCDE",
            "well_known": {
                "m.homeserver": {
                    "base_url": "https://matrix.slade360.uat.slade360edi.com/"
                }
            },
            "_cache_key": "2d0340b3bfedb72dfcb845e8d32b31b7",
        }

        org = baker.make(Organisation)
        org_2 = baker.make(Organisation)
        user1 = USER_MODEL.objects.create_user(
            email="john@doe.com", guid=uuid.uuid4(), password="hello_world6"
        )
        user2 = USER_MODEL.objects.create_user(
            email="john@doethesecond.com",
            guid=uuid.uuid4(),
            password="hello_world6",
        )
        person1 = Person.objects.create(
            first_name="Test",
            last_name="User",
            organisation=org,
            created_by=user1.pk,
            updated_by=user1.pk,
        )
        person2 = Person.objects.create(
            first_name="Test",
            last_name="User",
            organisation=org_2,
            created_by=user1.pk,
            updated_by=user1.pk,
        )
        UserProfile.objects.create(
            user=user1,
            person=person1,
            organisation=org,
            created_by=user1.pk,
            updated_by=user1.pk,
        )
        UserProfile.objects.create(
            user=user2,
            person=person2,
            organisation=org_2,
            created_by=user1.pk,
            updated_by=user1.pk,
        )

        self.client.login(username="john@doe.com", password="hello_world6")
        url = reverse("user-list")
        response = self.client.get(url)
        assert response.data["count"] == 1
