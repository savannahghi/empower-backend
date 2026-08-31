"""Test Opt Out Flow en."""
from unittest.mock import patch

from django.urls import reverse
from model_bakery import baker
from rest_framework import status
from rest_framework.test import APIClient

from sil_advantage.common.models.common_models import Person
from sil_advantage.notifications.models import USSDCode
from sil_advantage.patients.models import Patient
from tests.common.test_common_views import LoggedInMixin


class USSDFlowTests(LoggedInMixin):
    """Test USSD flow."""

    def setUp(self):
        """Setup Test Environment."""
        super().setUp()
        self.client = APIClient()
        self.org = self.global_organisation
        self.person = baker.make(Person, organisation=self.org)
        self.ussd_code = baker.make(
            USSDCode, ussd_code="*123*45#", organisation=self.org
        )
        self.patient = baker.make(Patient, person=self.person, organisation=self.org)

    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager."
        "PatientManager.check_patient_exists"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager."
        "PatientManager.opt_out_patient"
    )
    def test_opt_out_success(self, mock_opt_out_patient, mock_check_patient_exists):
        """Test successful opt-out flow."""
        mock_check_patient_exists.return_value = self.patient
        mock_opt_out_patient.return_value = True

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
        request_data["data"]["response"] = "1*3"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Kindly confirm that you want to opt out of the program.\n"
            "1. Confirm\n2. Reject",
            response.data["data"]["detail"],
        )

        # Confirm Opt Out
        request_data["data"]["response"] = "1*3*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "END You have successfully opted out.",
            response.data["data"]["detail"],
        )

    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager."
        "PatientManager.check_patient_exists"
    )
    def test_opt_out_cancel(self, mock_check_patient_exists):
        """Test opt-out cancellation."""
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
        request_data["data"]["response"] = "1*3"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Kindly confirm that you want to opt out of the program.\n"
            "1. Confirm\n2. Reject",
            response.data["data"]["detail"],
        )

        # Cancel Opt Out
        request_data["data"]["response"] = "1*3*2"
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

    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager."
        "PatientManager.check_patient_exists"
    )
    def test_opt_out_invalid_selection(self, mock_check_patient_exists):
        """Test invalid selection during opt-out."""
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
        request_data["data"]["response"] = "1*3"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Kindly confirm that you want to opt out of the program.\n"
            "1. Confirm\n2. Reject",
            response.data["data"]["detail"],
        )

        # Invalid Opt Out Selection
        request_data["data"]["response"] = "1*3*3"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Kindly confirm that you want to opt out of the program.\n"
            "1. Confirm\n2. Reject",
            response.data["data"]["detail"],
        )

    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager."
        "PatientManager.check_patient_exists"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager."
        "PatientManager.opt_out_patient"
    )
    def test_english_opt_out_error(
        self, mock_opt_out_patient, mock_check_patient_exists
    ):
        """Test error during opt-out in English."""
        mock_check_patient_exists.return_value = self.patient
        mock_opt_out_patient.return_value = False

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
            "CON Please select a service:\n1. View My Details\n2. Enroll "
            "to Health Education\n3. Opt out of Uzazi Salama",
            response.data["data"]["detail"],
        )

        # Select Opt Out
        request_data["data"]["response"] = "1*3"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Kindly confirm that you want to opt out of the program.\n"
            "1. Confirm\n2. Reject",
            response.data["data"]["detail"],
        )

        # Confirm Opt Out
        request_data["data"]["response"] = "1*3*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "END Opt-out failed. Please try again.",
            response.data["data"]["detail"],
        )
