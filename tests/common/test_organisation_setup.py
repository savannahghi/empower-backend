"""Tests for organisation model."""
import uuid
from unittest import mock

import orjson
from django.urls import reverse
from model_bakery import baker

from sil_advantage.common.models import Organisation
from sil_advantage.sil_auth.models import SILUser
from tests.common.test_common_views import LoggedInMixin

http_origin_header = {"HTTP_ORIGIN": "http://sil_advantage.com"}


class TestOrganisationSetup(LoggedInMixin):
    """Tests for organisation setup."""

    def setUp(self):
        """Create test organisation."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        super().setUp()

    def extra_headers(self):
        """Add token to authenticate a user agent with a server."""
        return {"HTTP_AUTHORIZATION": "token"}

    def test_patch_organisation_default_currency_none(self):
        """Create a test of organisation."""
        org = baker.make(Organisation, organisation_name="Sil Devs", slade_code=1)
        assert org.natural_key() == 1
        update_org_dict = {"organisation_name": "Coptic"}
        url = reverse("organisation-detail", kwargs={"pk": org.pk})
        response = self.client.patch(url, update_org_dict)

        assert response.status_code == 200
        returned_organization = response.data["organisation_name"]
        new_organization_name = update_org_dict["organisation_name"]
        assert returned_organization == new_organization_name

    def test_put_organisation_default_currency_none(self):
        """Test update organisation detals."""
        org = baker.make(Organisation, organisation_name="Sil Devs")
        update_org_dict = {
            "organisation_name": "Coptic",
            "active": True,
            "created_by": self.user.pk,
            "updated_by": self.user.pk,
            "slade_code": 2001,
            "phone_number": "+254721585473",
            "default_country": "KEN",
            "email_address": "me@me.com",
            "financial_year_start_date": "2016-11-07",
        }
        url = reverse("organisation-detail", kwargs={"pk": org.pk})
        response = self.client.put(url, update_org_dict)
        assert response.status_code == 200
        returned_organization = response.data["organisation_name"]
        new_organization_name = update_org_dict["organisation_name"]
        assert returned_organization == new_organization_name

    def test_organisation_setup(self):
        """Test to create an organisation.

        When a new organisation is created, two emails are sent and
        an Organisation admin is created with a workstation with type
        administrator.
        """
        url = reverse("organisation-setup-organisation")
        organisation_data = {
            "organisation_name": "Org ya tests",
            "created_by": self.user.pk,
            "updated_by": self.user.pk,
            "phone_number": "+254721585473",
            "slade_code": 2001,
            "default_country": "KEN",
            "email_address": "me@me.com",
            "financial_year_start_date": "2016-11-07",
        }
        self.make_user_super_admin()
        response = self.client.post(url, organisation_data, **http_origin_header)
        assert response.status_code == 201

    def test_organisation_setup_fail(self):
        """Test bad organisation fail."""
        url = reverse("organisation-setup-organisation")
        organisation_data = {}
        response = self.client.post(url, organisation_data, **http_origin_header)

        err_msg = "This field is required."
        assert response.status_code == 400
        assert response.data["organisation_name"][0] == err_msg

    @mock.patch("requests.request")
    def test_system_data_on_org_setup(self, mock_request):
        """Test that when new organisation is created,system data is loaded."""
        url = reverse("organisation-setup-organisation")
        organisation_data = {
            "organisation_name": "Org ya tests",
            "created_by": self.user.pk,
            "updated_by": self.user.pk,
            "phone_number": "+254721585473",
            "default_country": "KEN",
            "slade_code": 2001,
            "email_address": "me@me.com",
            "financial_year_start_date": "2016-11-07",
        }
        data = {
            "first_name": "first_name",
            "last_name": "last_name",
            "email": "i@m.com",
            "guid": str(uuid.uuid4()),
        }
        self.make_user_super_admin()
        mock_request.return_value = mock.MagicMock(
            status_code=201,
            response=orjson.dumps(data).decode("utf-8"),
            json=lambda: data,
        )

        response = self.client.post(url, organisation_data, **http_origin_header)
        assert response.status_code == 201
