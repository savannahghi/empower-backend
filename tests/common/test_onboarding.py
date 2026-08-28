"""Tests for onboarding."""
import uuid
from unittest.mock import MagicMock, patch

from django.urls import reverse
from model_bakery import baker
from rest_framework import status
from sil_edge_connection.exceptions import RequestFailure

from sil_advantage.common import models
from sil_advantage.common.constants import (
    ONBOARDING_SESSION_LEVEL_STATUSES,
    ORGANISATION_DOES_NOT_EXIST_CODE,
    ORGANISATION_EXISTS_CODE,
    ORGANISATION_ONBOARDING_PREFERENCES,
    ORGANIZATION_ONBOARDING_STATUSES,
    QUESTION_STRUCTURE_TYPES,
    QUESTION_TYPES,
)
from sil_advantage.sil_auth.models import SILUser
from tests.common.test_common_views import LoggedInMixin


class TestOnboardingView(LoggedInMixin):
    """Tests for organisation setup."""

    def setUp(self):
        """Test Onboarding setup."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        super().setUp()

    @patch("sil_advantage.common.api_clients.auth_server.ApiConnection")
    def test_registration_existing_business_partner(self, mock_auth_create_user):
        """Test to onboard a provider.

        When a new provider is on-boarded, an administrator is created
        in congrous.
        """
        # make unauthenticated requests
        self.client.logout()

        mock_auth = MagicMock()
        mock_auth.call.return_value = {
            "id": 4,
            "guid": "a0c6e047-99f2-464a-95f3-6dbbbf2037d2",
            "email": "admin@healthics.com",
            "first_name": "Mind",
            "last_name": "Health",
            "agreed_to_terms": True,
            "business_partner": "1",
        }

        mock_auth_create_user.return_value = mock_auth

        assert models.Organisation.objects.filter(slade_code="1").exists() is False

        data = {
            "provider": {
                "name": "Mind Healthics",
                "slade_code": "1",
                "country_id": "a0c6e047-99f2-464a-95f3-6dbbbf2037d2",
            },
            "email": "admin@healthics.com",
            "phone_number": "+254721585473",
            "first_name": "Mind",
            "last_name": "Health",
            "password": "pass123",
            "confirm_password": "pass123",
            "agreed_to_terms": True,
        }
        url = reverse("onboarding-registration")

        response = self.client.post(url, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "admin@healthics.com"
        assert response.data["agreed_to_terms"] is True

        assert models.Organisation.objects.filter(slade_code="1").exists() is True

    @patch("sil_advantage.common.api_clients.auth_server.ApiConnection")
    def test_registration_existing_business_partner_failure(
        self, mock_auth_create_user
    ):
        """Test to onboard a provider.

        When a new provider is on-boarded, an administrator is created
        in congrous.
        """
        # make unauthenticated requests
        self.client.logout()

        mock_auth = MagicMock()
        mock_auth.call.side_effect = RequestFailure(
            "invalid",
            {
                "status_code": 400,
                "response": "Bad Request",
                "method": "POST",
                "url": "/maybe",
                "request": "req",
                "payload": '{ "password": "password is too common" }',
            },
        )
        mock_auth_create_user.return_value = mock_auth

        assert models.Organisation.objects.filter(slade_code="1").exists() is False

        data = {
            "provider": {
                "name": "Mind Healthics",
                "slade_code": "1",
                "country_id": "a0c6e047-99f2-464a-95f3-6dbbbf2037d2",
            },
            "email": "admin@healthics.com",
            "phone_number": "+254721585473",
            "first_name": "Mind",
            "last_name": "Health",
            "password": "pass123",
            "confirm_password": "pass123",
            "agreed_to_terms": True,
        }
        url = reverse("onboarding-registration")

        response = self.client.post(url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # check org is not created
        assert models.Organisation.objects.filter(slade_code="1").exists() is False

    @patch("sil_advantage.common.api_clients.auth_server.ApiConnection")
    @patch("sil_advantage.common.api_clients.chargemaster.ChargeMaster")
    def test_registration_new_business_partner(
        self, mock_cm_client, mock_auth_create_user
    ):
        """Test to onboard a provider.

        When a new provider is on-boarded, an administrator is created
        in congrous.
        """
        # make unauthenticated requests
        self.client.logout()

        mock_auth = MagicMock()
        mock_auth.call.return_value = {
            "id": 4,
            "guid": "a0c6e047-99f2-464a-95f3-6dbbbf2037d2",
            "email": "admin@healthics.com",
            "first_name": "Mind",
            "last_name": "Health",
            "agreed_to_terms": True,
            "business_partner": "007",
        }

        mock_auth_create_user.return_value = mock_auth

        mock_cm = MagicMock()
        mock_cm.business_partners.create.return_value = {"slade_code_counter": "007"}
        mock_cm_client.return_value = mock_cm

        assert models.Organisation.objects.filter(slade_code="007").exists() is False

        data = {
            "provider": {
                "name": "Mind Healthics",
                "country_id": "a0c6e047-99f2-464a-95f3-6dbbbf2037d2",
            },
            "email": "admin@healthics.com",
            "phone_number": "+254721585473",
            "first_name": "Mind",
            "last_name": "Health",
            "password": "pass123",
            "confirm_password": "pass123",
            "agreed_to_terms": True,
        }
        url = reverse("onboarding-registration")

        response = self.client.post(url, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "admin@healthics.com"
        assert response.data["agreed_to_terms"] is True

        assert models.Organisation.objects.filter(slade_code="007").exists() is True

        new_org = models.Organisation.objects.get(slade_code="007")
        assert new_org.organisation_name == "Mind Healthics"

        onboarding = models.OrganisationOnboarding.objects.get(organisation=new_org)
        assert onboarding is not None
        assert onboarding.organisation == new_org
        assert (
            onboarding.verification_status == ORGANIZATION_ONBOARDING_STATUSES.PENDING
        )
        assert (
            onboarding.onboarding_session_level
            == ONBOARDING_SESSION_LEVEL_STATUSES.INTERESTS
        )

    @patch("sil_advantage.common.api_clients.chargemaster.ChargeMaster")
    def test_registration_new_business_partner_failure(self, mock_cm_client):
        """Test to onboard a provider.

        When a new provider is on-boarded, an administrator is created
        in congrous.
        """
        # make unauthenticated requests
        self.client.logout()

        mock_cm = MagicMock()
        mock_cm.business_partners.create.side_effect = RequestFailure(
            "invalid",
            {
                "status_code": 400,
                "response": "Bad Request",
                "method": "POST",
                "url": "/maybe",
                "request": "req",
                "payload": '{ "password": "password is too common" }',
            },
        )
        mock_cm_client.return_value = mock_cm

        assert models.Organisation.objects.filter(slade_code="007").exists() is False

        data = {
            "provider": {
                "name": "Mind Healthics",
                "country_id": "a0c6e047-99f2-464a-95f3-6dbbbf2037d2",
            },
            "email": "admin@healthics.com",
            "phone_number": "+254721585473",
            "first_name": "Mind",
            "last_name": "Health",
            "password": "pass123",
            "confirm_password": "pass123",
            "agreed_to_terms": True,
        }
        url = reverse("onboarding-registration")

        response = self.client.post(url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        assert models.Organisation.objects.filter(slade_code="007").exists() is False

    def test_registration_invalid_input(self):
        """Test registration with invalid input."""
        # make unauthenticated requests
        self.client.logout()

        data = {
            "provider": {"name": "Mind Healthics", "slade_code": "1"},
            "email": "healthics.com",
            "phone_number": "+254721585473",
            "first_name": "Mind",
            "last_name": "Health",
            "password": "pass123",
            "confirm_password": "pass123",
            "agreed_to_terms": True,
        }
        url = reverse("onboarding-registration")

        response = self.client.post(url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Enter a valid email address." in str(response.json())

    @patch("sil_advantage.common.api_clients.chargemaster.ChargeMaster")
    def test_search_for_business_partner_successful_call(
        self, mock_get_chargemaster_client
    ):
        """Test successful proxy search to chargemaster."""
        # make unauthenticated requests
        self.client.logout()

        url = reverse("onboarding-provider-search")
        search_param = "Robin+Muhia"

        mock_client_instance = MagicMock()
        mock_get_chargemaster_client.return_value = mock_client_instance
        id = uuid.uuid4()
        mock_business_partners_list = MagicMock(
            return_value={
                "count": 1,
                "next": None,
                "previous": None,
                "page_size": 100,
                "current_page": 1,
                "total_pages": 1,
                "start_index": 1,
                "end_index": 1,
                "results": [
                    {
                        "id": id,
                        "name": "Dr Robin Muhia GOAT Doctor",
                        "slade_code_counter": 0000,
                        "slade_code": "PRO-0000",
                    }
                ],
            }
        )
        mock_client_instance.business_partners.list = mock_business_partners_list

        response = self.client.get(url, data={"search": search_param})

        mock_business_partners_list.assert_called_once_with(
            filters={
                "active": True,
                "fields": "id,slade_code,slade_code_counter,name",
                "bp_type": "PROVIDER",
                "is_branch": False,
                "search": [search_param],
            }
        )

        assert response.status_code == 200
        assert response.data
        data = response.data
        assert data["count"] == 1
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["id"] == id
        assert result["name"] == "Dr Robin Muhia GOAT Doctor"
        assert result["slade_code_counter"] == 0000
        assert result["slade_code"] == "PRO-0000"

    @patch("sil_advantage.common.api_clients.chargemaster.ChargeMaster")
    def test_search_for_business_partner_unsuccessful_call(self, mock_cm_client):
        """Test failure for search for a business partner."""
        # make unauthenticated requests
        self.client.logout()

        mock_cm = MagicMock()
        mock_cm.business_partners.list.side_effect = RequestFailure(
            "invalid",
            {
                "status_code": 400,
                "response": "Bad Request",
                "method": "GET",
                "url": "/maybe",
                "request": "req",
                "payload": '{ "error": "Unauthenticated request" }',
            },
        )
        mock_cm_client.return_value = mock_cm
        url = reverse("onboarding-provider-search")
        search_param = "Robin+Muhia"
        response = self.client.get(url, data={"search": search_param})

        assert response.status_code == 400
        assert response.data == "Bad Request"

    @patch("sil_advantage.common.api_clients.chargemaster.ChargeMaster")
    def test_retrieval_of_countries_from_chargemaster(
        self, mock_get_chargemaster_client
    ):
        """Test successful retrieval of countries from chargemaster."""
        # make unauthenticated requests
        self.client.logout()

        url = reverse("onboarding-available-countries")

        mock_client_instance = MagicMock()
        mock_get_chargemaster_client.return_value = mock_client_instance
        mock_countries_list = MagicMock(
            return_value={
                "count": 4,
                "next": None,
                "previous": None,
                "page_size": 100,
                "current_page": 1,
                "total_pages": 1,
                "start_index": 1,
                "end_index": 4,
                "results": [
                    {"id": "d5aa75ef-f020-4c5f-962f-1aebdc441539", "name": "KENYA"},
                    {"id": "4509ebe5-fc51-4bde-ab04-5f08bd81bfec", "name": "RWANDA"},
                    {"id": "2175aca2-8802-4124-ba05-7f5844fd3788", "name": "TANZANIA"},
                    {"id": "8d8b42e6-6354-4393-bd1c-775d196c04e5", "name": "UGANDA"},
                ],
            }
        )
        mock_client_instance.countries.list = mock_countries_list

        response = self.client.get(url)

        mock_countries_list.assert_called_once_with(
            filters={
                "fields": "id,name",
            }
        )

        assert response.status_code == 200
        assert response.data
        data = response.data
        assert data["count"] == 4
        assert len(data["results"]) == 4
        assert data["results"][0]["name"] == "KENYA"
        assert data["results"][1]["name"] == "RWANDA"
        assert data["results"][2]["name"] == "TANZANIA"
        assert data["results"][3]["name"] == "UGANDA"

    @patch("sil_advantage.common.api_clients.chargemaster.ChargeMaster")
    def test_retrieval_failure_of_countries_from_chargemaster(self, mock_cm_client):
        """Test failure for retrieval of countries from chargemaster."""
        # make unauthenticated requests
        self.client.logout()

        mock_cm = MagicMock()
        mock_cm.countries.list.side_effect = RequestFailure(
            "invalid",
            {
                "status_code": 400,
                "response": "Bad Request",
                "method": "GET",
                "url": "/maybe",
                "request": "req",
                "payload": '{ "error": "Unauthenticated request" }',
            },
        )
        mock_cm_client.return_value = mock_cm
        url = reverse("onboarding-available-countries")
        response = self.client.get(url)

        assert response.status_code == 400
        assert response.data == "Bad Request"

    def test_querying_organisation_existence(self):
        """Test the existence of org on advantage."""
        baker.make(
            models.Organisation, organisation_name="Jujutsu Kaisen", slade_code=1001
        )
        url = reverse("onboarding-organisation-check")
        # make unauthenticated requests
        self.client.logout()
        # no name
        response = self.client.post(url)
        assert response.status_code == 400
        # correct name
        data = {"name": "Jujutsu Kaisen"}
        response = self.client.post(url, data=data)
        assert response.status_code == 200
        assert response.data["code"] == ORGANISATION_EXISTS_CODE
        assert response.data["message"] == "Organisation already exists"
        # correct name and correct slade code
        data = {"name": "Jujutsu Kaisen", "slade_code": 1001}
        response = self.client.post(url, data=data)
        assert response.status_code == 200
        assert response.data["code"] == ORGANISATION_EXISTS_CODE
        assert response.data["message"] == "Organisation already exists"

        # incorrect slade code but correct name
        data = {"name": "Jujutsu Kaisen", "slade_code": 1002}
        response = self.client.post(url, data=data)
        assert response.status_code == 200
        assert response.data["code"] == ORGANISATION_EXISTS_CODE
        assert response.data["message"] == "Organisation already exists"

        # incorrect name but correct slade code
        data = {"name": "Demon Slayers", "slade_code": 1001}
        response = self.client.post(url, data=data)
        assert response.status_code == 200
        assert response.data["code"] == ORGANISATION_EXISTS_CODE
        assert response.data["message"] == "Organisation already exists"

        data = {"name": "Demon Slayers"}
        response = self.client.post(url, data=data)
        assert response.status_code == 200
        assert response.data["message"] == "Organisation does not exist"
        assert response.data["code"] == ORGANISATION_DOES_NOT_EXIST_CODE


class TestOrganisationOnboardingView(LoggedInMixin):
    """Test case of Organisation Onboarding ViewSet."""

    def setUp(self):
        """Test setup suite."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.provider_onboarding = models.OrganisationOnboarding.objects.get(
            organisation=self.global_organisation
        )
        self.maxDiff = None
        super().setUp()

    def test_querying_preferences_for_a_new_provider(self):
        """Test interest get endpoint for a new org in INTERESTS session level."""
        url = reverse(
            "organisationonboarding-detail", kwargs={"pk": self.provider_onboarding.pk}
        )
        response = self.client.get(url)
        assert response.status_code == 200
        assert (
            response.data["onboarding_session_level"]
            == ONBOARDING_SESSION_LEVEL_STATUSES.INTERESTS
        )
        preferences = response.data["preferences"]
        questions = preferences["questions"]
        assert len(questions) == len(ORGANISATION_ONBOARDING_PREFERENCES)
        assert questions[0] == ORGANISATION_ONBOARDING_PREFERENCES[0]
        assert questions[1] == list(ORGANISATION_ONBOARDING_PREFERENCES[1])

    def test_querying_prefereces_for_provider_in_final_review(self):
        """Test retrieval of preferences that have already been recorded.

        The org is in the final review submission level.
        """
        preferences = self.provider_onboarding.preferences
        questions = preferences["questions"]
        questions[0]["choices"][0]["selected"] = True
        questions[0]["choices"][1]["selected"] = True
        questions[1][0]["choices"][4]["selected"] = True
        questions[1][0]["choices"][2]["selected"] = True
        self.provider_onboarding.save()

        url = reverse(
            "organisationonboarding-detail", kwargs={"pk": self.provider_onboarding.pk}
        )

        self.provider_onboarding.onboarding_session_level = (
            ONBOARDING_SESSION_LEVEL_STATUSES.FINAL_REVIEW_AND_SUBMISSION
        )
        self.provider_onboarding.save()
        response = self.client.get(url)
        assert response.status_code == 200
        assert (
            response.data["onboarding_session_level"]
            == ONBOARDING_SESSION_LEVEL_STATUSES.FINAL_REVIEW_AND_SUBMISSION
        )
        preferences = response.data["preferences"]
        questions = preferences["questions"]
        assert len(questions) == len(ORGANISATION_ONBOARDING_PREFERENCES)
        assert questions[0] != ORGANISATION_ONBOARDING_PREFERENCES[0]
        assert questions[1] != ORGANISATION_ONBOARDING_PREFERENCES[1]
        assert questions[0]["choices"][0]["selected"] is True
        assert questions[0]["choices"][1]["selected"] is True
        assert questions[1][0]["choices"][4]["selected"] is True
        assert questions[1][0]["choices"][2]["selected"] is True

    def test_patching_preferences(self):
        """Test patching preferences."""
        preferences = [
            {
                "question_text": "How would you like to use AfyaMoja?",
                "choices": [
                    {"1": "To manage bookings and appointments", "selected": True},
                    {"2": "To communicate with my clients", "selected": False},
                    {"3": "To post shifts", "selected": False},
                    {"4": "To find open shifts", "selected": True},
                ],
                "question_type": QUESTION_TYPES.INTERESTS,
                "question_structure": QUESTION_STRUCTURE_TYPES.MULTICHOICE_CLOSE_ENDED,
            },
            {
                "question_text": "Which of these topics would you be interested in?",
                "choices": [
                    {"1": "Cancer", "selected": True},
                    {"2": "Diabetes", "selected": False},
                    {"3": "Hypertension", "selected": True},
                    {"4": "Wellness and fitness", "selected": False},
                    {"5": "ICD10", "selected": False},
                    {"6": "Nutrionist", "selected": True},
                ],
                "question_type": QUESTION_TYPES.TOPIC,
                "question_structure": QUESTION_STRUCTURE_TYPES.MULTICHOICE_CLOSE_ENDED,
            },
        ]
        onboarding_session_level = ONBOARDING_SESSION_LEVEL_STATUSES.BASIC_DETAILS
        data = {
            "provider_onboarding": str(self.provider_onboarding.id),
            "verification_status": self.provider_onboarding.verification_status,
            "onboarding_session_level": onboarding_session_level,
            "preferences": preferences,
        }
        url = reverse(
            "organisationonboarding-detail", kwargs={"pk": self.provider_onboarding.pk}
        )
        response = self.client.patch(url, data=data)
        assert response.status_code == 200
        self.provider_onboarding.refresh_from_db()
        assert (
            self.provider_onboarding.onboarding_session_level
            == ONBOARDING_SESSION_LEVEL_STATUSES.BASIC_DETAILS
        )
