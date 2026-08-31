"""Test Change language."""
from unittest.mock import patch

from django.urls import reverse
from model_bakery import baker
from rest_framework import status
from rest_framework.test import APIClient

from sil_advantage.common.models.common_models import OperatingRegion, Person
from sil_advantage.notifications.models import USSDCode
from sil_advantage.notifications.ussd.handlers.ussd_handler import USSDHandler
from sil_advantage.patients.models import Patient
from tests.common.test_common_views import LoggedInMixin


class USSDFlowTestsLanguageChange(LoggedInMixin):
    """Test USSD flow."""

    def setUp(self):
        """Setup Test Environment."""
        super().setUp()
        self.client = APIClient()
        self.org = self.global_organisation
        self.ussd_code = baker.make(
            USSDCode,
            ussd_code="*123*45#",
            organisation=self.org,
            updated_by=self.org.id,
            created_by=self.org.id,
        )
        self.region = OperatingRegion.objects.create(
            name="Test Region",
            unit_type="COUNTY",
            organisation=self.org,
            updated_by=self.org.id,
            created_by=self.org.id,
        )
        self.person = Person.objects.create(
            first_name="John",
            last_name="Doe",
            date_of_birth="1990-01-01",
            gender="MALE",
            associated_region=self.region,
            organisation=self.org,
            updated_by=self.org.id,
            created_by=self.org.id,
            language="en",  # Initial language is English
        )
        self.patient = baker.make(Patient, person=self.person, organisation=self.org)

    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager.PatientManager.check_patient_exists"
    )
    def test_language_change(self, mock_check_patient_exists):
        """Test successful change language flow."""
        mock_check_patient_exists.return_value = self.patient

        # Start the session and select the language
        request_data = {
            "type": "USSD_MESSAGE",
            "data": {
                "guid": "ab9d3266-c746-4016-81ac-a0c349f8e8cb",
                "code": "*123*45#",
                "gateway": "SAFARICOM",
                "msisdn": "+254712345678",
                "response": "",
                "state": "",
            },
        }
        url = reverse("ussd_view")
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Welcome to Uzazi Salama, please select your preferred "
            "language to proceed:\n1. English\n2. Kiswahili",
            response.data["data"]["detail"],
        )

        # Select English language
        request_data["data"]["response"] = "1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Please select a service:\n"
            "1. View My Details\n"
            "2. Enroll to Health Education\n"
            "3. Opt out of Uzazi Salama\n"
            "4. Change Language\n",
            response.data["data"]["detail"],
        )

        # Select Opt Out
        request_data["data"]["response"] = "1*4"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Welcome to Uzazi Salama, please select your preferred "
            "language to proceed:\n1. English\n2. Kiswahili",
            response.data["data"]["detail"],
        )

        # Select Kiswahili
        request_data["data"]["response"] = "1*4*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Chagua Huduma:\n1. Tazama maelezo yangu\n2. Jisajili kwa elimu\n"
            "3. Chagua kutoka kwa programu ya Uzazi Salama\n4. Badilisha Lugha\n",
            response.data["data"]["detail"],
        )
        # Reload the person instance from the database and check the language
        self.person.refresh_from_db()
        self.assertEqual(self.person.language, "sw")

    def test_language_change_registration(self):
        """Test successful language change during registration."""
        # Start the session and select the language
        request_data = {
            "type": "USSD_MESSAGE",
            "data": {
                "guid": "ab9d3266-c746-4016-81ac-a0c349f8e8cb",
                "code": "*123*45#",
                "gateway": "SAFARICOM",
                "msisdn": "+254712345678",
                "response": "",
                "state": "",
            },
        }
        url = reverse("ussd_view")
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Welcome to Uzazi Salama, please select your preferred "
            "language to proceed:\n1. English\n2. Kiswahili",
            response.data["data"]["detail"],
        )

        # Select English language
        request_data["data"]["response"] = "1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Please select a service:\n1. Register Myself\n2. Change Language",
            response.data["data"]["detail"],
        )

        # Select Opt Out
        request_data["data"]["response"] = "1*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Welcome to Uzazi Salama, please select your preferred "
            "language to proceed:\n1. English\n2. Kiswahili",
            response.data["data"]["detail"],
        )

        # Select Kiswahili
        request_data["data"]["response"] = "1*4*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Tafadhali chagua huduma:\n1. Jisajili\n2. Badilisha Lugha",
            response.data["data"]["detail"],
        )

    @patch("sil_advantage.notifications.ussd.handlers.ussd_handler.logger")
    @patch("sil_advantage.common.models.common_models.Person.save")
    def test_update_person_language_with_exceptions(self, mock_save, mock_logger):
        """Test exception when modifying person language."""
        mock_save.side_effect = Exception("Save failed")
        session = {
            "patient_details": self.patient,
            "language": "sw",
        }
        USSDHandler._update_language_for_person(
            session=session, phone_number="+24512112112", ussd_code="*123*45#"
        )
        mock_logger.error.assert_called_once_with(
            "Error updating language for person ID: Save failed"
        )
