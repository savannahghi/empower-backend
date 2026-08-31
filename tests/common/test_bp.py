"""Tests for OAUTH."""
from unittest import mock

import orjson
import pytest
from django.urls import reverse
from model_bakery import baker
from social_django import models

from tests.common.test_common_views import LoggedInMixin


class TestBpProxy(LoggedInMixin):
    """Tests for Bp Proxy."""

    @mock.patch("requests.request")
    def test_get_bp_reg_from_server(self, mock_request):
        """Test access token authorises resource access."""
        baker.make(
            models.UserSocialAuth,
            user=self.user,
            provider="sil-oauth2",
            extra_data={"access_token": "hgdh78-yADg665"},
        )
        data = {
            "results": [
                {
                    "id": "42133e99-8bbe-4aa3-9800-c02dabd9d0f3",
                    "name": "Savannah",
                    "slade_code": 1,
                }
            ]
        }
        mock_request.return_value = mock.MagicMock(
            status_code=200,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )
        url = reverse("bpregistry-list")
        response = self.client.get(url)
        assert response.json() == data

    @mock.patch("requests.request")
    def test_get_bp_reg_fails(self, mock_request):
        """Test invalid access token doesn't access resources."""
        baker.make(
            models.UserSocialAuth,
            user=self.user,
            provider="sil-oauth2",
            extra_data={"access_token": "hgdh78-yADg665"},
        )
        mock_request.return_value = mock.MagicMock(
            status_code=404, response="{}", json={}
        )
        url = reverse("bpregistry-list")

        with pytest.raises(TypeError):
            response = self.client.get(url)
            response.json()
