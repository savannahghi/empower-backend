"""Test auth connection."""
from unittest import mock

from model_bakery import baker
from social_django.models import UserSocialAuth

from sil_advantage.common.api_clients import make_request
from sil_advantage.common.models import Organisation
from tests.common.test_common_views import LoggedInMixin


class TestAuthConnection(LoggedInMixin):
    """Test suite for testing auth connection functions."""

    @mock.patch("requests.request")
    def test_post_and_patch_adds_organisation_login_user(self, mock_request):
        """Test for post and patch of organisation login user."""
        request = type(
            "RequestObj",
            (object,),
            {
                "data": {},
                "query_params": {},
                "META": {"HTTP_AUTHORIZATION": "Bearer token"},
                "user": self.user,
            },
        )()
        headers = {
            "Authorization": "Bearer token",
            "Content-Type": "application/json",
            "Accept": "application/json, */*",
        }

        mock_request.return_value = mock.MagicMock(
            status_code=200, response="{}", json=lambda: {}
        )
        # post
        make_request("post", "https://test@test.com", request)
        data = '{"organisation":"' + str(self.user.organisation.id) + '"}'
        mock_request.assert_called_with(
            "POST",
            "https://test@test.com",
            headers=headers,
            params={},
            data=data,
        )

        # patch
        make_request("patch", "https://test@test.com", request)
        data = '{"organisation":"' + str(self.user.organisation.id) + '"}'
        mock_request.assert_called_with(
            "PATCH",
            "https://test@test.com",
            headers=headers,
            params={},
            data=data,
        )

    @mock.patch("requests.request")
    def test_prefers_organisation_in_payload_super_user(self, mock_request):
        """Test organisation user authentication.

        It should use the organisation in the payload if the user is a
        cross network admin.
        """
        self.make_user_super_admin()
        new_org = baker.make(Organisation)
        request = type(
            "RequestObj",
            (object,),
            {
                "data": {},
                "query_params": {},
                "META": {"HTTP_AUTHORIZATION": "Bearer token"},
                "user": self.user,
            },
        )()
        headers = {
            "Accept": "application/json, */*",
            "Content-Type": "application/json",
            "Authorization": "Bearer token",
        }

        mock_request.return_value = mock.MagicMock(
            status_code=200, response="{}", json=lambda: {}
        )
        # post
        make_request(
            "post",
            "https://test@test.com",
            request,
            {"organisation": str(new_org.pk)},
        )
        data = '{"organisation":"' + str(new_org.id) + '"}'
        mock_request.assert_called_with(
            "POST",
            "https://test@test.com",
            headers=headers,
            params={},
            data=data,
        )

    @mock.patch("requests.request")
    def test_uses_users_organisation_default(self, mock_request):
        """Test logged in user authentication.

        It should use the organisation of the user currently logged in even
        if an organisation is passed in the payload
        """
        request = type(
            "RequestObj",
            (object,),
            {
                "data": {},
                "query_params": {},
                "META": {"HTTP_AUTHORIZATION": "Bearer token"},
                "user": self.user,
            },
        )()
        headers = {
            "Accept": "application/json, */*",
            "Content-Type": "application/json",
            "Authorization": "Bearer token",
        }

        mock_request.return_value = mock.MagicMock(
            status_code=200, response="{}", json=lambda: {}
        )
        # post
        make_request(
            "post",
            "https://test@test.com",
            request,
            {"organisation": "d866a404-fc84-430f-a65b-06adc0491658"},
        )
        data = '{"organisation":"' + str(self.user.organisation.id) + '"}'
        mock_request.assert_called_with(
            "POST",
            "https://test@test.com",
            headers=headers,
            params={},
            data=data,
        )

    @mock.patch("requests.request")
    def test_query_params_included_in_req(self, mock_request):
        """Test passed parameters in the request."""
        request = type(
            "RequestObj",
            (object,),
            {
                "data": {},
                "query_params": {"fields": "id"},
                "META": {"HTTP_AUTHORIZATION": "Bearer token"},
                "user": self.user,
            },
        )()
        headers = {
            "Accept": "application/json, */*",
            "Content-Type": "application/json",
            "Authorization": "Bearer token",
        }

        mock_request.return_value = mock.MagicMock(
            status_code=200, response="{}", json=lambda: {}
        )
        # post
        make_request("get", "https://test@test.com", request, {})
        mock_request.assert_called_with(
            "GET",
            "https://test@test.com",
            headers=headers,
            params={"fields": "id"},
            data={},
        )

    @mock.patch("requests.request")
    def test_token_from_header(self, mock_request):
        """Test token present in returned header."""
        request = type(
            "RequestObj",
            (object,),
            {
                "data": {},
                "query_params": {"fields": "id"},
                "META": {"HTTP_AUTHORIZATION": "Bearer token123"},
                "user": self.user,
            },
        )()
        headers = {
            "Accept": "application/json, */*",
            "Content-Type": "application/json",
            "Authorization": "Bearer token123",
        }

        mock_request.return_value = mock.MagicMock(
            status_code=200, response="{}", json=lambda: {}
        )
        # post
        make_request("get", "https://test@test.com", request, {})
        mock_request.assert_called_with(
            "GET",
            "https://test@test.com",
            headers=headers,
            params={"fields": "id"},
            data={},
        )

    @mock.patch("requests.request")
    def test_token_from_social_auth_model(self, mock_request):
        """Test token from social django model."""
        data = {"access_token": "token123model"}
        baker.make(
            UserSocialAuth,
            user=self.user,
            extra_data=data,
            provider="sil-oauth2",
        )
        request = type(
            "RequestObj",
            (object,),
            {
                "data": {},
                "query_params": {"fields": "id"},
                "META": {},
                "user": self.user,
            },
        )()
        headers = {
            "Accept": "application/json, */*",
            "Content-Type": "application/json",
            "Authorization": "Bearer token123model",
        }

        mock_request.return_value = mock.MagicMock(
            status_code=200, response="{}", json=lambda: {}
        )
        # post
        make_request("GET", "https://test@test.com", request, {})
        mock_request.assert_called_with(
            "GET",
            "https://test@test.com",
            headers=headers,
            params={"fields": "id"},
            data={},
        )
