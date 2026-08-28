"""Test authentication views."""
import json
import uuid
from unittest.mock import MagicMock, patch

import orjson
import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.http import HttpResponse
from django.test import TestCase, override_settings
from model_bakery import baker
from nio import AsyncClient
from rest_framework import status
from rest_framework.reverse import reverse
from social_django import models

from sil_advantage.common.models import (
    Organisation,
    OrganisationOnboarding,
    OrgUnit,
    OTPVerificationStatus,
    Person,
    PersonContact,
    PersonOTP,
    UserProfile,
)
from sil_advantage.sil_auth.models import (
    MFAStatus,
    MFAType,
    SILUser,
    SILUserMFA,
)
from tests.common.test_common_views import LoggedInMixin
from tests.common.utility import AsyncMagicMock, PicklableMagicMock, patch_baker

USER_MODEL = get_user_model()
http_origin_header = {"HTTP_ORIGIN": "http://sil_advantage.com"}


class ThroughTableBase:
    """Abstracted class to test simple through tables."""

    def test_create(self):
        """Test create a model."""
        instance_one = baker.make(self.model_one["name"])
        instance_two = baker.make(self.model_two["name"])
        var_one = self.model_one["var"]
        var_two = self.model_two["var"]
        data = {var_one: instance_one.pk, var_two: instance_two.pk}

        if self.organisation:
            data["organisation"] = self.organisation.pk

        response = self.client.post(self.url_list, data)

        assert response.status_code == 201
        assert response.data[var_two] == data[var_two]
        assert response.data[var_one] == data[var_one]

    def test_retrieve(self):
        """Test retrieve a model."""
        if self.organisation:
            baker.make(self.test_model, organisation=self.organisation)
            baker.make(self.test_model, organisation=self.organisation)
        else:
            baker.make(self.test_model)
            baker.make(self.test_model)

        response = self.client.get(self.url_list)
        assert response.data["count"] == 2

    def test_patch(self):
        """Test change model data."""
        instance_one = baker.make(self.model_one["name"])
        if self.organisation:
            test_insta = baker.make(self.test_model, organisation=self.organisation)
        else:
            test_insta = baker.make(self.test_model)
        var_one = self.model_one["var"]
        data = {var_one: instance_one.pk}

        url = reverse(self.url_detail, kwargs={"pk": test_insta.pk})

        response = self.client.patch(url, data)
        assert response.status_code == 200
        assert response.data[var_one] == data[var_one]

    def test_put(self):
        """Test replace model data."""
        if self.organisation:
            test_insta = baker.make(self.test_model, organisation=self.organisation)
        else:
            test_insta = baker.make(self.test_model)
        instance_one = baker.make(self.model_one["name"])
        instance_two = baker.make(self.model_two["name"])
        var_one = self.model_one["var"]
        var_two = self.model_two["var"]

        data = {var_one: instance_one.pk, var_two: instance_two.pk}

        if self.organisation:
            data["organisation"] = self.organisation.pk

        url = reverse(self.url_detail, kwargs={"pk": test_insta.pk})
        response = self.client.put(url, data)

        assert response.status_code == 200
        assert response.data[var_two] == data[var_two]


class ThroughTableDeleteMixin:
    """Table delete mixin.

    Test deletes in through tables. This method has been created separately
    from the Class ThroughTableBase since not all thorough tables support
    true deletes.
    """

    def test_delete(self):
        """Test delete a model."""
        if self.organisation:
            insta1 = baker.make(self.test_model, organisation=self.global_organisation)
            baker.make(self.test_model, organisation=self.global_organisation)
        else:
            insta1 = baker.make(self.test_model)
            baker.make(self.test_model)
        url = reverse(self.url_detail, kwargs={"pk": insta1.pk})
        self.client.delete(url)
        response = self.client.get(self.url_list)

        assert response.data["count"] == 1


class SILUserTestCase(TestCase):
    """Test case for the user model."""

    def test_user_properties(self):
        """Test user email roperty."""
        user = USER_MODEL.objects.create_user(
            guid=uuid.uuid4(), email="test@test.com", password="Insecure"
        )
        user.save()
        assert str(user) == "test@test.com"

    def test_user_manager(self):
        """Test user manager."""
        user_manger = USER_MODEL.objects

        user = user_manger.create_user(guid=uuid.uuid4(), email="test@test.com")
        self.assertTrue(user.pk)
        super_user = user_manger.create_superuser(
            guid=uuid.uuid4(), email="superuser@test.com"
        )
        assert super_user.is_admin

    def test_email_is_required(self):
        """Test user has an email."""
        organisation = baker.make(Organisation)
        test_data = {"organisation": organisation, "guid": uuid.uuid4()}
        user_manger = USER_MODEL.objects
        with pytest.raises(ValueError):
            user_manger.create_user(**test_data)
        with pytest.raises(ValueError):
            user_manger.create_superuser(**test_data)


@override_settings(MATRIX_SECRET="a-secret")
class UserViewTestCase(LoggedInMixin):
    """Test case for the user view."""

    def setUp(self):
        """Test set up."""
        super().setUp()
        self.url = reverse("user-list")
        values = {"organisation": self.user.organisation}
        patcher = patch_baker(values=values)
        patcher.start()
        self.addCleanup(patcher.stop)

    def extra_headers(self):
        """Extra URL headers."""
        return {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
            "HTTP_AUTHORIZATION": "token",
        }

    @patch("requests.request")
    def test_create_user(self, mock_request):
        """Test create a user."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        data = {
            "guid": str(uuid.uuid4()),
            "email": "test99@gmail.com",
            "first_name": "Sheldon",
            "last_name": "Cooper",
            "roles": [{"id": 1}, {"id": 2}, {"id": 4}],
            "password": "password",
            "confirm_password": "password",
        }
        mock_request.return_value = MagicMock(
            status_code=201,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.post(self.url, data, **http_origin_header)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "test99@gmail.com"
        assert get_user_model().objects.filter(email="test99@gmail.com").exists()

    @patch.object(AsyncClient, "set_displayname", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "login", new_callable=AsyncMagicMock)
    @patch(
        "sil_advantage.notifications.matrix.requests",
        new_callable=PicklableMagicMock,
    )
    def test_list_users(
        self,
        mock_matrix_requests,
        mock_login,
        mock_set_matrix_display_name,
    ):
        """Test retrieve list of users."""
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
        baker.make(get_user_model(), _quantity=5)

        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 2
        mock_set_matrix_display_name.assert_called_once_with(
            "Jesse Pinkman",
        )

    @patch("requests.request")
    def test_list_users_detail_endpoint(self, mock_request):
        """Test retrieve user details."""
        data = {
            "guid": str(self.user.guid),
            "email": "test99@gmail.com",
            "first_name": "Sheldon",
            "last_name": "Cooper",
            "roles": [{"id": 1}, {"id": 2}, {"id": 4}],
            "password": "password",
            "confirm_password": "password",
        }
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        url = reverse("user-detail", kwargs={"guid": str(self.user.guid)})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK


@override_settings(MATRIX_SECRET="a-secret")
class TestMeEndpoint(LoggedInMixin):
    """Test case for user endpoint."""

    def extra_headers(self):
        """Return an empty headers list."""
        return {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    @patch(
        "sil_advantage.notifications.matrix.requests",
        new_callable=PicklableMagicMock,
    )
    def test_should_return_details_logged_in_user(
        self,
        mock_matrix_requests,
    ):
        """Test details of a logged in user."""
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
        onboarding = OrganisationOnboarding.objects.get(
            organisation=self.global_organisation
        )
        onboarding.delete()
        url = reverse("me")
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["email"] == self.user.email
        assert response.data["clinical_org_id"] is None
        assert response.data["clinical_facility_id"] is None
        assert response.data["matrix_user_id"] == matrix_uid
        assert response.data["organisation_onboarding"] is None

        expected_keys = [
            "id",
            "first_name",
            "last_name",
            "full_name",
            "person_id",
            "organisation_name",
            "organisation_id",
            "pk",
            "organisation_email_address",
            "last_login",
            "email",
            "guid",
            "is_network_admin",
            "is_admin",
            "is_staff",
            "active",
            "created",
            "updated",
            "permissions",
            "is_active",
            "business_partner",
            "matrix_token",
            "organisation_onboarding",
        ]
        for expected_key in expected_keys:
            assert expected_key in response.data

        cache.delete(self.user.profile._cache_key)
        org = self.global_organisation
        org.tenant_id = "fc2270cb-dadf-40ae-a9ef-14c42c17ce0f"
        org.save()
        baker.make(
            OrgUnit,
            organisation=org,
            erp_id="9f273420-b325-475c-a1a5-0dd268eeffb1",
            facility_id="bda9242c-c579-4102-828a-a5476a38e74d",
            orgunit_type="branch",
        )

        response = self.client.get(url)
        self.assertEqual(
            str(response.data["clinical_org_id"]),
            "fc2270cb-dadf-40ae-a9ef-14c42c17ce0f",
        )
        self.assertEqual(
            str(response.data["clinical_facility_id"]),
            "bda9242c-c579-4102-828a-a5476a38e74d",
        )
        onboarding = baker.make(OrganisationOnboarding, organisation=org)
        url = reverse("me")
        response = self.client.get(url)
        assert response.status_code == 200
        organisation_onboarding = response.data["organisation_onboarding"]
        assert organisation_onboarding["status"] == onboarding.verification_status
        assert (
            organisation_onboarding["session_level"]
            == onboarding.onboarding_session_level
        )
        assert organisation_onboarding["id"] == onboarding.id

    @patch(
        "sil_advantage.notifications.matrix.requests",
        new_callable=PicklableMagicMock,
    )
    def test_matrix_error(
        self,
        mock_matrix_requests,
    ):
        """Test /me with a Matrix error."""
        mock_matrix_requests.post.side_effect = Exception(
            "acha hizo stori zako",
        )

        url = reverse("me")
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["matrix_token"] is None


class RoleViewTest(LoggedInMixin):
    """Test case for role view."""

    def setUp(self):
        """Test set up."""
        self.url_list = reverse("role-list")
        super().setUp()

    def extra_headers(self):
        """Extra url headers."""
        return {"HTTP_AUTHORIZATION": "token"}

    @patch("requests.request")
    def test_create_role(self, mock_request):
        """Test create a new role."""
        organisation = baker.make(Organisation)
        data = {
            "name": "Doctor",
            "role_permissions": [{"id": 1}],
            "description": "description",
            "organisation": str(organisation.pk),
        }

        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )

        response = self.client.post(self.url_list, data)
        assert response.status_code == 200
        assert response.data["name"] == data["name"]
        assert response.data["description"] == data["description"]

    @patch("requests.request")
    def test_create_role_permission_names(self, mock_request):
        """Test create a role with a name."""
        organisation = baker.make(Organisation)
        data = {
            "name": "Doctor",
            "templates": [{"id": "org_admin"}],
            "description": "description",
            "organisation": str(organisation.pk),
        }

        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )

        response = self.client.post(self.url_list, data)
        assert response.status_code == 200
        assert response.data["name"] == data["name"]
        assert response.data["description"] == data["description"]

    @patch("requests.request")
    def test_create_role_no_perms(self, mock_request):
        """Test a role has to have permission(s)."""
        organisation = baker.make(Organisation)
        data = {
            "name": "Doctor",
            "description": "description",
            "organisation": str(organisation.pk),
        }

        mock_request.return_value = MagicMock(
            status_code=400, response="{}", json=lambda: {}
        )

        response = self.client.post(self.url_list, data)
        assert response.status_code == 400

    @patch("requests.request")
    def test_list_roles(self, mock_request):
        """Test retrieve a list of roles."""
        data = {
            "results": [
                {
                    "id": "42133e99-8bbe-4aa3-9800-c02dabd9d0f3",
                    "name": "Nurse",
                    "description": "The nurse role",
                }
            ]
        }
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.get(self.url_list)
        assert response.status_code == 200
        assert response.data == data

    @patch("requests.request")
    def test_retrieve_role_detail(self, mock_request):
        """Test retrieve details of a role."""
        data = {
            "id": "42133e99-8bbe-4aa3-9800-c02dabd9d0f3",
            "name": "Nurse",
            "description": "The nurse role",
        }
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        url = reverse("role-detail", kwargs={"pk": 4})
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data == data

    @patch("requests.request")
    def test_patch_role(self, mock_request):
        """Test chande details of a role."""
        data = {
            "id": "42133e99-8bbe-4aa3-9800-c02dabd9d0f3",
            "name": "Nurse",
            "description": "The nurse role",
        }
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        role_name = {"name": "role2"}
        url = reverse("role-detail", kwargs={"pk": 5})
        response = self.client.patch(url, role_name)

        assert response.status_code == 200
        assert response.data["name"] == "Nurse"

    @patch("requests.request")
    def test_patch_role_with_perms(self, mock_request):
        """Test change permissins for a role."""
        data = {
            "id": "42133e99-8bbe-4aa3-9800-c02dabd9d0f3",
            "name": "Nurse",
            "role_permissions": [{"id": 1}],
            "description": "The nurse role",
        }
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        role_name = {"name": "role2", "role_permissions": [{"id": 1}]}
        url = reverse("role-detail", kwargs={"pk": 5})
        response = self.client.patch(url, role_name)

        assert response.status_code == 200
        assert response.data["role_permissions"] == [{"id": 1}]

    @patch("requests.request")
    def test_delete_role(self, mock_request):
        """Test delete a role."""
        baker.make(
            models.UserSocialAuth,
            user=self.user,
            provider="sil-oauth2",
            extra_data={"access_token": "token"},
        )
        mock_request.return_value = MagicMock(
            status_code=204,
            response="{}",
            json=lambda: (_ for _ in ()).throw(orjson.JSONDecodeError("", "", 1)),
            text="",
        )
        url = reverse("role-detail", kwargs={"pk": 5})
        response = self.client.delete(url)
        assert response.status_code == 204

    @patch("requests.request")
    def test_handle_request_json_decode_error(self, mock_request):
        """Handle JsonDecodeErrors."""
        baker.make(
            models.UserSocialAuth,
            user=self.user,
            provider="sil-oauth2",
            extra_data={"access_token": "token"},
        )
        mock_request.return_value = MagicMock(
            status_code=200,
            response="{}",
            json=lambda: (_ for _ in ()).throw(json.decoder.JSONDecodeError("", "", 1)),
            text="",
        )
        url = reverse("rolepermissions-detail", kwargs={"pk": 6})
        response = self.client.delete(url)
        assert response.status_code == 200

    @patch("requests.request")
    def test_handle_file_attachments_from_remote_calls(self, mock_request):
        """Handle JsonDecodeErrors."""
        baker.make(
            models.UserSocialAuth,
            user=self.user,
            provider="sil-oauth2",
            extra_data={"access_token": "token"},
        )
        response = HttpResponse(
            content=b"x0123/some binary data/xx45012",
        )
        response.status_code = 200
        response.headers = {
            "Content-Disposition": "attachment; filename=foo.pdf",
            "Content-Type": "application/pdf",
        }
        response.text = "x0123/some binary data/xx45012"
        mock_request.return_value = response
        url = reverse("erp", kwargs={"resource": "roles/users"})
        response = self.client.get(url)
        assert response.status_code == 200


class PermissionViewTest(LoggedInMixin):
    """Tesst case for permission view."""

    def setUp(self):
        """Test set up."""
        super().setUp()
        self.url_list = reverse("permission-list")

    def extra_headers(self):
        """Extra url headers."""
        return {"HTTP_AUTHORIZATION": "token"}

    @patch("requests.request")
    def test_list_perm(self, mock_request):
        """Test retrieve list of permissions."""
        data = {
            "results": [
                {
                    "id": "42133e99-8bbe-4aa3-9800-c02dabd9d0f3",
                    "name": "sil_advantage.list_person",
                    "description": "Person perm",
                }
            ]
        }
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.get(self.url_list)
        assert response.status_code == 200
        assert response.data == data

    @patch("requests.request")
    def test_list_perm_with_page_size(self, mock_request):
        """Test list permission by page size."""
        data = {
            "results": [
                {
                    "id": "42133e99-8bbe-4aa3-9800-c02dabd9d0f3",
                    "name": "sil_advantage.list_person",
                    "description": "Person perm",
                }
            ]
        }
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.get(self.url_list, {"page_size": 50})
        assert response.status_code == 200
        assert response.data == data


class TestCreateUser(LoggedInMixin):
    """Test case for creating a user."""

    def setUp(self):
        """Test set up."""
        super().setUp()
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.url = reverse("user-list")

    def extra_headers(self):
        """Extra URL headers."""
        return {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
            "HTTP_AUTHORIZATION": "token",
        }

    @patch("requests.request")
    def test_create_a_user_successfully(self, mock_request):
        """Test create a new user."""
        data = {
            "email": "some@user.com",
            "guid": str(uuid.uuid4()),
            "first_name": "Test",
            "last_name": "Last",
            "roles": [{"id": 1}, {"id": 4}],
            "password": "password",
            "confirm_password": "password",
        }

        mock_request.return_value = MagicMock(
            status_code=201,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.post(self.url, data, **http_origin_header)
        assert response.status_code == 201, str(response.data)
        assert get_user_model().objects.filter(email="some@user.com").exists()
        assert response.data["email"] == "some@user.com"
        assert len(mail.outbox) == 1

    @patch("requests.request")
    def test_create_a_user_fails(self, mock_request):
        """Test user creation fails.

        If the request to the auth server to create a user is not successful
        then the user is not created.
        """
        data = {
            "email": "some@user.com",
            "guid": str(uuid.uuid4()),
            "first_name": "Test",
            "last_name": "Last",
            "roles": [{"id": 1}, {"id": 4}],
            "password": "password",
            "confirm_password": "password",
        }

        mock_request.return_value = MagicMock(
            status_code=400,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.post(self.url, data, **http_origin_header)
        assert response.status_code == 400
        assert not get_user_model().objects.filter(email="some@user.com").exists()
        assert len(mail.outbox) == 0

    @patch("requests.request")
    def test_create_a_user_no_roles(self, mock_request):
        """Test user must have role when created."""
        data = {
            "email": "some@user.com",
            "guid": str(uuid.uuid4()),
            "first_name": "Test",
            "last_name": "Last",
            "password": "password",
            "confirm_password": "password",
        }

        mock_request.return_value = MagicMock(
            status_code=400,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.post(self.url, data, **http_origin_header)
        assert response.status_code == 400
        assert not get_user_model().objects.filter(email="some@user.com").exists()

    @patch("requests.request")
    def test_create_a_user_in_diff_org(self, mock_request):
        """Test create user.

        A user in a different organisation can be created
        by specifing the organisation field.
        """
        self.make_user_super_admin()
        org = baker.make(Organisation)
        data = {
            "email": "fuser@user.com",
            "guid": str(uuid.uuid4()),
            "first_name": "Test",
            "last_name": "Last",
            "roles": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}],
            "organisation": str(org.pk),
            "password": "password",
            "confirm_password": "password",
        }
        mock_request.return_value = MagicMock(
            status_code=201,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.post(self.url, data, **http_origin_header)
        assert response.status_code == 201, str(response.data)
        assert response.data["email"] == "fuser@user.com"
        # the user is created in that organisation
        user_organisation = (
            get_user_model().objects.get(email="fuser@user.com").organisation
        )
        assert user_organisation == org
        assert len(mail.outbox) == 1

    @patch("requests.request")
    def test_validation_error_if_organisation_does_not_exist(self, mock_req):
        """Test validate a user.

        If ``organisation`` is defined and it doesn't exist an error
        is thrown.
        """
        self.make_user_super_admin()
        data = {
            "guid": str(uuid.uuid4()),
            "email": "some@user.com",
            "first_name": "Test",
            "last_name": "Last",
            "roles": [{"id": 1}, {"id": 3}, {"id": 5}],
            "organisation": "4943fad9-d8ec-48b0-b8e9-12e3f643fef7",
        }
        mock_req.return_value = MagicMock(
            status_code=400,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.post(self.url, data, **http_origin_header)
        assert response.status_code == 400
        assert response.data["organisation"][0] == (
            "Ensure the organisation provided exists."
        )
        assert len(mail.outbox) == 0

    @patch("requests.request")
    def test_validation_if_user_has_no_perms_user_org_used(self, mock_request):
        """Test validate a user.

        If a user supplies ``organisation`` and they lack the
        permission ``is_multi_organisation_admin`` the organisation they
        are currently logged into is used.
        """
        data = {
            "guid": str(uuid.uuid4()),
            "email": "some@user.com",
            "first_name": "Test",
            "last_name": "Last",
            "roles": [{"id": 1}, {"id": 3}, {"id": 5}],
            "organisation": str(self.user.organisation.id),
            "password": "password",
            "confirm_password": "password",
        }
        mock_request.return_value = MagicMock(
            status_code=201,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.post(self.url, data, **http_origin_header)
        assert response.status_code == 201
        user_organisation = (
            get_user_model().objects.get(email="some@user.com").organisation
        )
        assert user_organisation == self.user.organisation
        assert len(mail.outbox) == 1


class TestUpdateUser(LoggedInMixin):
    """Test case for updating a user."""

    def setUp(self):
        """Test set up."""
        super().setUp()
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        person = baker.make(
            Person,
            first_name="first",
            last_name="last",
            organisation=self.user.organisation,
        )
        self.user_test = baker.make(get_user_model())
        baker.make(
            UserProfile,
            person=person,
            user=self.user_test,
            organisation=person.organisation,
        )
        self.url = reverse("user-detail", kwargs={"guid": self.user_test.guid})

    def extra_headers(self):
        """Extra url headers."""
        return {"HTTP_AUTHORIZATION": "token"}

    @patch("requests.request")
    def test_update_user(self, mock_request):
        """Test validate person update details."""
        data = {"first_name": "John"}
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.patch(self.url, data)
        cache.delete(self.user_test.profile._cache_key)
        assert response.status_code == 200
        self.user_test = get_user_model().objects.get(pk=self.user_test.pk)
        assert self.user_test.person.first_name == "John"
        assert response.data["first_name"] == data["first_name"]

        data = {"last_name": "Mark II"}
        response = self.client.patch(self.url, data)
        cache.delete(self.user_test.profile._cache_key)
        assert response.status_code == 200
        self.user_test = get_user_model().objects.get(pk=self.user_test.pk)
        assert self.user_test.person.last_name == "Mark II"

    @patch("requests.request")
    def test_update_user_fail(self, mock_request):
        """Test update fails.

        If an update to the auth server fails the the changes should not be
        made to the database as well.
        """
        data = {"first_name": "John"}
        mock_request.return_value = MagicMock(
            status_code=400,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        before_update = self.user_test.person.first_name
        response = self.client.patch(self.url, data)
        assert response.status_code == 400
        self.user_test.refresh_from_db()
        assert self.user_test.person.first_name == before_update

    @patch("requests.request")
    def test_update_user_email(self, mock_request):
        """Test validate user's update details."""
        data = {"email": "john@mark.com"}
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.patch(self.url, data)
        assert response.status_code == 200
        self.user_test.refresh_from_db()
        assert self.user_test.email == "john@mark.com"

    @patch("requests.request")
    def test_update_user_roles(self, mock_request):
        """Test update a user role."""
        data = {"first_name": "John", "roles": [{"id": "1"}]}
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.patch(self.url, data)
        assert response.status_code == 200
        assert response.data["roles"] == data["roles"]


class RolePermissionViewTest(LoggedInMixin):
    """Test case for role permissions."""

    def setUp(self):
        """Test set up."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.url_list = reverse("rolepermissions-list")
        super().setUp()

    def extra_headers(self):
        """Extra url headers."""
        return {"HTTP_AUTHORIZATION": "token"}

    @patch("requests.request")
    def test_create_roleperms(self, mock_request):
        """Test create role permissions."""
        organisation = baker.make(Organisation)
        data = {
            "role": 1,
            "permission": 2,
            "organisation": str(organisation.pk),
        }

        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )

        response = self.client.post(self.url_list, data)
        assert response.status_code == 200

    @patch("requests.request")
    def test_list_roleperms(self, mock_request):
        """Test retrieve list of role permissions."""
        data = {
            "results": [
                {
                    "id": "42133e99-8bbe-4aa3-9800-c02dabd9d0f3",
                    "role": 1,
                    "permission": 2,
                }
            ]
        }
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        response = self.client.get(self.url_list)
        assert response.status_code == 200
        assert response.data == data

    @patch("requests.request")
    def test_retrieve_roleperms_detail(self, mock_request):
        """Test retrieve details of a role permission."""
        data = {
            "id": "42133e99-8bbe-4aa3-9800-c02dabd9d0f3",
            "role": 1,
            "permission": 2,
        }
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        url = reverse("rolepermissions-detail", kwargs={"pk": 4})
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data == data

    @patch("requests.request")
    def test_patch_rolepermissions(self, mock_request):
        """Test change details of a role permission."""
        data = {
            "id": "42133e99-8bbe-4aa3-9800-c02dabd9d0f3",
            "role": 1,
            "permission": 2,
        }
        mock_request.return_value = MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        role_name = {"permission": 3}
        url = reverse("rolepermissions-detail", kwargs={"pk": 5})
        response = self.client.patch(url, role_name)

        assert response.status_code == 200

    @patch("requests.request")
    def test_delete_role(self, mock_request):
        """Test delete a role."""
        baker.make(
            models.UserSocialAuth,
            user=self.user,
            provider="sil-oauth2",
            extra_data={"access_token": "token"},
        )
        mock_request.return_value = MagicMock(
            status_code=204,
            response="{}",
            json=lambda: (_ for _ in ()).throw(orjson.JSONDecodeError("", "", 1)),
            text="",
        )
        url = reverse("rolepermissions-detail", kwargs={"pk": 5})
        response = self.client.delete(url)
        assert response.status_code == 204


class UserMFAViewTest(LoggedInMixin):
    """Test for User ID view."""

    def setUp(self):
        """Create test user."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        super().setUp()

    def test_send_otp(self):
        """Test sending an MFA OTP."""
        organisation = self.global_organisation
        user = baker.make(
            get_user_model(), email="gaines.edmund@them.show", guid=uuid.uuid4()
        )
        person = baker.make(
            Person, first_name="Edmund", last_name="Gaines", organisation=organisation
        )
        baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254722060000",
        )
        baker.make(
            UserProfile,
            user=user,
            person=person,
            organisation=organisation,
        )

        mfa = baker.make(
            SILUserMFA,
            user=user,
            mfa_type=MFAType.PHONE_OTP,
        )

        url = reverse("silusermfa-send-otp", kwargs={"pk": mfa.id})
        response = self.client.post(url)

        assert response.status_code == 200

        mfa.refresh_from_db()
        assert mfa.otp is not None

    def test_verify_otp(self):
        """Test verifying an MFA OTP."""
        organisation = self.global_organisation
        user = baker.make(
            get_user_model(), email="gaines.edmund@them.show", guid=uuid.uuid4()
        )
        person = baker.make(
            Person, first_name="Edmund", last_name="Gaines", organisation=organisation
        )
        baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254722060000",
        )
        baker.make(
            UserProfile,
            user=user,
            person=person,
            organisation=organisation,
        )

        otp = baker.make(
            PersonOTP,
            person=person,
            code="354658",
            verification_status=OTPVerificationStatus.PENDING,
            expires_at=None,
        )

        mfa = baker.make(
            SILUserMFA,
            user=user,
            otp=otp,
            mfa_type=MFAType.PHONE_OTP,
        )

        url = reverse("silusermfa-verify-otp", kwargs={"pk": mfa.id})

        response = self.client.post(url, data={"code": "354658"})
        assert response.status_code == 200
        assert response.data["status"] == OTPVerificationStatus.VERIFIED

        mfa.refresh_from_db()
        assert mfa.status == MFAStatus.ENABLED

        otp.refresh_from_db()
        assert otp.verification_status == OTPVerificationStatus.VERIFIED

        # same otp verification
        response_two = self.client.post(url, data={"code": "354658"})
        assert response_two.status_code == 400

        otp_two = baker.make(
            PersonOTP,
            person=person,
            code="354655",
            verification_status=OTPVerificationStatus.PENDING,
            expires_at=None,
        )

        mfa.otp = otp_two
        mfa.save()

        # new otp verification
        response_three = self.client.post(url, data={"code": "354655"})
        assert response_three.status_code == 200
