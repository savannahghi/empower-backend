"""USSD English views."""
from unittest.mock import patch

from django.urls import reverse
from model_bakery import baker
from rest_framework import status
from rest_framework.test import APIClient

from sil_advantage.common.models.common_models import Person
from sil_advantage.notifications.models import USSDCode
from sil_advantage.segments.models.segments import Segment
from tests.common.test_common_views import LoggedInMixin


class USSDFlowTests(LoggedInMixin):
    """Test USSD flow."""

    def setUp(self):
        """Setup Test Environment."""
        super().setUp()
        self.client = APIClient()
        self.org = self.global_organisation
        self.person = baker.make(Person, organisation=self.org)
        self.segment1 = baker.make(
            Segment, name="Segment 1", organisation=self.org, created_by=self.user.id
        )
        self.segment2 = baker.make(
            Segment, name="Segment 2", organisation=self.org, created_by=self.user.id
        )
        self.segment3 = baker.make(
            Segment, name="Segment 3", organisation=self.org, created_by=self.user.id
        )
        self.segment4 = baker.make(
            Segment, name="Segment 4", organisation=self.org, created_by=self.user.id
        )
        self.ussd_code = baker.make(
            USSDCode, ussd_code="*123*45#", organisation=self.org
        )

    @patch(
        "sil_advantage.notifications.ussd.managers.operation_region_manager.RegionManager.get_operating_regions"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager."
        "PatientManager.create_patient"
    )
    def test_english_flow(self, mock_create_patient, mock_get_available_regions):
        """Test English registration flow."""
        mock_create_patient.return_value = True
        mock_get_available_regions.return_value = [
            "Kilifi North",
            "Kilifi South",
        ]

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
            "CON Welcome to Uzazi Salama, please select your preferred"
            " language to proceed:\n1. English\n2. Kiswahili",
            response.data["data"]["detail"],
        )

        # Select Invalid language
        request_data["data"]["response"] = "3"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Welcome to Uzazi Salama, please select your preferred"
            " language to proceed:\n1. English\n2. Kiswahili",
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

        # Invalid Input
        request_data["data"]["response"] = "1*3"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Please select a service:\n1. Register Myself\n2. Change Language",
            response.data["data"]["detail"],
        )

        # Select "Register Myself
        request_data["data"]["response"] = "1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Select your region:\n1. Kilifi North\n2. Kilifi South\n"
            "0. Back to Main Menu",
            response.data["data"]["detail"],
        )
        request_data["data"]["response"] = "1*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON To register, please enter your first and last name "
            "(Eg Jane Kaberu):\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Enter invalid name
        request_data["data"]["response"] = "1*1*1*John"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Invalid input. Please enter correct data for enter_name again.",
            response.data["data"]["detail"],
        )

        # Enter name
        request_data["data"]["response"] = "1*1*1*John Doe"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Enter Date of Birth (DD/MM/YYYY):\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )
        # Invalid Date of Birth
        request_data["data"]["response"] = "1*1*1*John Doe*01/01/"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Invalid input. Please enter correct data for enter_dob again.",
            response.data["data"]["detail"],
        )

        # Enter Date of Birth
        request_data["data"]["response"] = "1*1*1*John Doe*01/01/1990"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Select Gender:\n1. Male\n2. Female\n3. Other\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )
        # Confirm registration
        request_data["data"]["response"] = "1*1*1*John Doe*01/01/1990*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Confirm registration to Uzazi Salama program:\n"
            "Name: John Doe\n"
            "Date of Birth: 01/01/1990\n"
            "Gender: Male\n\n"
            "1. Confirm\n2. Cancel\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Invalid registration confirmation prompts you again
        request_data["data"]["response"] = "1*1*1*John Doe*01/01/1990*1*1*3"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Confirm registration to Uzazi Salama program:\n"
            "Name: John Doe\n"
            "Date of Birth: 01/01/1990\n"
            "Gender: Male\n\n"
            "1. Confirm\n2. Cancel\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Confirm consent
        request_data["data"]["response"] = "1*1*1*John Doe*01/01/1990*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Would you like to receive SMS from Uzazi Salama? "
            "Select 1 to accept or 2 to reject:\n"
            "1. Accept\n"
            "2. Reject\n\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )
        # Confirm Registration
        request_data["data"]["response"] = "1*1*1*John Doe*01/01/1990*1*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "END You have successfully been registered to Uzazi Salama. "
            "You will receive an SMS shortly confirming your registration.",
            response.data["data"]["detail"],
        )
        mock_create_patient.assert_called_once_with(
            first_name="John",
            last_name="Doe",
            date_of_birth="01/01/1990",
            gender="1",
            phone_number="+254712345678",
            consent_status="VERIFIED",
            ussd_code="*123*45#",
            associated_region="Kilifi North",
            language="en",
        )

    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager."
        "PatientManager.create_patient"
    )
    def test_cancel_registration_english(self, mock_create_patient):
        """Test cancel registration in English."""
        mock_create_patient.return_value = True

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
            "CON Welcome to Uzazi Salama, please select your "
            "preferred language to proceed:\n1. English\n2. Kiswahili",
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

        # Select "Register Myself"
        request_data["data"]["response"] = "1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON To register, please enter your first and last name "
            "(Eg Jane Kaberu):\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Enter name
        request_data["data"]["response"] = "1*1*John Doe"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Enter Date of Birth (DD/MM/YYYY):",
            response.data["data"]["detail"],
        )

        # Enter Date of Birth
        request_data["data"]["response"] = "1*1*John Doe*01/01/1990"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Select Gender:\n1. Male\n2. Female\n3. Other\n",
            response.data["data"]["detail"],
        )

        # Validate the consent selection
        request_data["data"]["response"] = "1*1*John Doe*01/01/1990*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Confirm registration to Uzazi Salama program:\n"
            "Name: John Doe\n"
            "Date of Birth: 01/01/1990\n"
            "Gender: Male\n\n"
            "1. Confirm\n2. Cancel\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Cancel Registration
        request_data["data"]["response"] = "1*1*John Doe*01/01/1990*1*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("END Registration cancelled.", response.data["data"]["detail"])
        mock_create_patient.assert_not_called()

    @patch(
        "sil_advantage.notifications.ussd.managers.operation_region_manager.RegionManager.get_operating_regions"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager."
        "PatientManager.create_patient"
    )
    def test_registration_failure_english(
        self, mock_create_patient, mock_get_available_regions
    ):
        """Test registration failure scenario."""
        mock_create_patient.return_value = False
        mock_get_available_regions.return_value = [
            "Kilifi North",
            "Kilifi South",
        ]

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

        # Select service
        request_data["data"]["response"] = "1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Please select a service:\n1. Register Myself\n2. Change Language",
            response.data["data"]["detail"],
        )

        # Select "Register Myself"
        request_data["data"]["response"] = "1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Select your region:\n1. Kilifi North\n2. Kilifi South"
            "\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )
        request_data["data"]["response"] = "1*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON To register, please enter your first and last name "
            "(Eg Jane Kaberu):\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Enter name
        request_data["data"]["response"] = "1*1*1*John Doe"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Enter Date of Birth (DD/MM/YYYY):",
            response.data["data"]["detail"],
        )

        # Enter Date of Birth
        request_data["data"]["response"] = "1*1*1*John Doe*01/01/1990"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Select Gender:\n1. Male\n2. Female\n3. Other\n",
            response.data["data"]["detail"],
        )

        # Validate the consent selection
        request_data["data"]["response"] = "1*1*1*John Doe*01/01/1990*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Confirm registration to Uzazi Salama program:\n"
            "Name: John Doe\n"
            "Date of Birth: 01/01/1990\n"
            "Gender: Male\n\n"
            "1. Confirm\n2. Cancel\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Validate the consent selection
        request_data["data"]["response"] = "1*1*1*John Doe*01/01/1990*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Would you like to receive SMS from Uzazi Salama? "
            "Select 1 to accept or 2 to reject:\n"
            "1. Accept\n"
            "2. Reject\n\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Confirm Registration
        request_data["data"]["response"] = "1*1*1*John Doe*01/01/1990*1*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "END Registration failed. Please try again.",
            response.data["data"]["detail"],
        )
        mock_create_patient.assert_called_once_with(
            first_name="John",
            last_name="Doe",
            date_of_birth="01/01/1990",
            gender="1",
            phone_number="+254712345678",
            consent_status="VERIFIED",
            ussd_code="*123*45#",
            associated_region="Kilifi North",
            language="en",
        )

    @patch(
        "sil_advantage.notifications.ussd.managers.operation_region_manager.RegionManager.get_operating_regions"
    )
    def test_back_menu(self, mock_get_available_regions):
        """Test English registration flow."""
        mock_get_available_regions.return_value = [
            "Kilifi North",
            "Kilifi South",
        ]
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
            "CON Welcome to Uzazi Salama, please select your preferred"
            " language to proceed:\n1. English\n2. Kiswahili",
            response.data["data"]["detail"],
        )

        # Select Invalid language
        request_data["data"]["response"] = "3"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Welcome to Uzazi Salama, please select your preferred"
            " language to proceed:\n1. English\n2. Kiswahili",
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

        # Invalid Input
        request_data["data"]["response"] = "1*3"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Please select a service:\n1. Register Myself\n2. Change Language",
            response.data["data"]["detail"],
        )

        # Select "Register Myself
        request_data["data"]["response"] = "1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Select your region:\n1. Kilifi North\n2. Kilifi South"
            "\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )
        request_data["data"]["response"] = "1*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON To register, please enter your first and last name "
            "(Eg Jane Kaberu):\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )
        # Select "Back to main menu
        request_data["data"]["response"] = "1*1*1*0"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Please select a service:\n1. Register Myself\n2. Change Language",
            response.data["data"]["detail"],
        )

    @patch(
        "sil_advantage.notifications.ussd.managers.operation_region_manager.RegionManager.get_operating_regions"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager."
        "PatientManager.create_patient"
    )
    def test_english_flow_no_regions(
        self, mock_create_patient, mock_get_available_regions
    ):
        """Test English registration flow with no available regions."""
        mock_create_patient.return_value = True
        mock_get_available_regions.return_value = []

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
            "CON Welcome to Uzazi Salama, please select your preferred"
            " language to proceed:\n1. English\n2. Kiswahili",
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

        # Select "Register Myself"
        request_data["data"]["response"] = "1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON To register, please enter your first and last name "
            "(Eg Jane Kaberu):\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Enter name
        request_data["data"]["response"] = "1*1*John Doe"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Enter Date of Birth (DD/MM/YYYY):\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Enter Date of Birth
        request_data["data"]["response"] = "1*1*John Doe*01/01/1990"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Select Gender:\n1. Male\n2. Female\n3. Other\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Confirm registration
        request_data["data"]["response"] = "1*1*John Doe*01/01/1990*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Confirm registration to Uzazi Salama program:\n"
            "Name: John Doe\n"
            "Date of Birth: 01/01/1990\n"
            "Gender: Male\n\n"
            "1. Confirm\n2. Cancel\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Confirm consent
        request_data["data"]["response"] = "1*1*John Doe*01/01/1990*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Would you like to receive SMS from Uzazi Salama? "
            "Select 1 to accept or 2 to reject:\n"
            "1. Accept\n"
            "2. Reject\n\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )

        # Confirm Registration
        request_data["data"]["response"] = "1*1*John Doe*01/01/1990*1*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "END You have successfully been registered to Uzazi Salama. "
            "You will receive an SMS shortly confirming your registration.",
            response.data["data"]["detail"],
        )
        mock_create_patient.assert_called_once_with(
            first_name="John",
            last_name="Doe",
            date_of_birth="01/01/1990",
            gender="1",
            phone_number="+254712345678",
            consent_status="VERIFIED",
            ussd_code="*123*45#",
            associated_region=None,
            language="en",
        )
