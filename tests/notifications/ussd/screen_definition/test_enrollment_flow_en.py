"""Test USSD enrollment English workflow."""

from unittest.mock import patch

from django.urls import reverse
from model_bakery import baker
from rest_framework import status
from rest_framework.test import APIClient

from sil_advantage.common.models import Person, PersonContact
from sil_advantage.notifications.models import USSDCode
from sil_advantage.patients.models import Patient
from sil_advantage.segments.models.segments import Segment
from tests.common.test_common_views import LoggedInMixin


class EnglishEnrollmentUSSDFlowTest(LoggedInMixin):
    """Test USSD enrollment English flow."""

    def setUp(self):
        """Setup Test Environment."""
        super().setUp()
        self.client = APIClient()
        self.org = self.global_organisation

        # Create segments
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
        # Create person
        self.person = baker.make(
            Person,
            first_name="John",
            last_name="Doe",
            date_of_birth="1990-01-01",
            gender="MALE",
        )
        # Add Person contact infor
        baker.make(
            PersonContact,
            person=self.person,
            contact_type="phone_number",
            contact="+254790360360",
        )
        # Create patient
        self.patient = baker.make(Patient, person=self.person, organisation=self.org)

        # Create USSDCode
        self.ussd_code = baker.make(
            USSDCode, ussd_code="*123*45#", organisation=self.org
        )

    @patch(
        "sil_advantage.notifications.ussd.managers.segment_manager.SegmentManager.add_person_to_segment"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.segment_manager.SegmentManager.get_available_segments_for_person"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager.PatientManager.check_patient_exists"
    )
    def test_enroll_to_education_english_success(
        self, mock_check_patient_exists, mock_get_segments, mock_add_person
    ):
        """Test enrollment for registered patient."""
        mock_check_patient_exists.return_value = self.patient
        mock_get_segments.return_value = [
            "Segment 1",
            "Segment 2",
            "Segment 3",
            "Segment 4",
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
            "CON Welcome to Uzazi Salama,"
            " please select your preferred language to proceed:"
            "\n1. English\n2. Kiswahili",
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
        # Select "Enroll to Education"
        request_data["data"]["response"] = "1*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Select a Category you would like to enroll to:"
            "\n1. Segment 1\n2. Segment 2\n3. Segment 3\n4. Segment 4",
            response.data["data"]["detail"],
        )

        # Select "Segment 2"
        request_data["data"]["response"] = "1*2*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Confirm Enrollment to Segment 2:\n1. Accept\n2. Reject",
            response.data["data"]["detail"],
        )

        # Confirm enrollment - success case
        mock_add_person.return_value = True
        request_data["data"]["response"] = "1*2*2*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "END You have been successfully enrolled to the Program."
            " You will receive an SMS shortly confirming your enrollment.\n",
            response.data["data"]["detail"],
        )

        # View my details"
        request_data["data"]["response"] = "1*1"
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

        # Opt out of the program
        request_data["data"]["response"] = "1*1*3"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Kindly confirm that you want to opt out of the program."
            "\n1. Confirm\n2. Reject",
            response.data["data"]["detail"],
        )

        # Reject opt out of the program
        request_data["data"]["response"] = "1*1*3*2"
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
        "sil_advantage.notifications.ussd.managers.operation_region_manager.RegionManager.get_operating_regions"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.segment_manager.SegmentManager.add_person_to_segment"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.segment_manager.SegmentManager.get_available_segments_for_person"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager.PatientManager.check_patient_exists"
    )
    def test_enroll_to_education_with_regions_success(
        self,
        mock_check_patient_exists,
        mock_get_segments,
        mock_add_person,
        mock_get_available_regions,
    ):
        """Test enrollment for registered patient."""
        mock_check_patient_exists.return_value = self.patient
        mock_get_segments.return_value = [
            "Segment 1",
            "Segment 2",
            "Segment 3",
            "Segment 4",
        ]
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
            "CON Welcome to Uzazi Salama,"
            " please select your preferred language to proceed:"
            "\n1. English\n2. Kiswahili",
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
        # Select "Enroll to Education"
        request_data["data"]["response"] = "1*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Select a Category you would like to enroll to:"
            "\n1. Segment 1\n2. Segment 2\n3. Segment 3\n4. Segment 4",
            response.data["data"]["detail"],
        )

        # Select "Segment 2"
        request_data["data"]["response"] = "1*2*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Confirm Enrollment to Segment 2:\n1. Accept\n2. Reject",
            response.data["data"]["detail"],
        )

        # Confirm enrollment - success case
        mock_add_person.return_value = True
        request_data["data"]["response"] = "1*2*2*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "END You have been successfully enrolled to the Program."
            " You will receive an SMS shortly confirming your enrollment.\n",
            response.data["data"]["detail"],
        )

    @patch(
        "sil_advantage.notifications.ussd.managers.segment_manager.SegmentManager.add_person_to_segment"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.segment_manager.SegmentManager.get_available_segments_for_person"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager.PatientManager.check_patient_exists"
    )
    def test_enrollment_flow_failure(
        self, mock_check_patient_exists, mock_get_segments, mock_add_person
    ):
        """Test enrollment for registered patient."""
        mock_check_patient_exists.return_value = self.patient
        mock_get_segments.return_value = [
            "Segment 1",
            "Segment 2",
            "Segment 3",
            "Segment 4",
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
            "CON Welcome to Uzazi Salama,"
            " please select your preferred language to proceed:"
            "\n1. English\n2. Kiswahili",
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
        # Select "Enroll to Education"
        request_data["data"]["response"] = "1*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Select a Category you would like to enroll to:"
            "\n1. Segment 1\n2. Segment 2\n3. Segment 3\n4. Segment 4",
            response.data["data"]["detail"],
        )

        # Select "Segment 2"
        request_data["data"]["response"] = "1*2*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Confirm Enrollment to Segment 2:\n1. Accept\n2. Reject",
            response.data["data"]["detail"],
        )

        # Confirm enrollment - Failure case
        mock_add_person.return_value = False
        request_data["data"]["response"] = "1*2*2*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "END Enrollment failed. Please try again.",
            response.data["data"]["detail"],
        )

    @patch(
        "sil_advantage.notifications.ussd.managers.segment_manager.SegmentManager.get_available_segments_for_person"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager.PatientManager.check_patient_exists"
    )
    def test_enroll_to_education_english_failed(
        self, mock_check_patient_exists, mock_get_segments
    ):
        """Test enrollment for registered patient."""
        mock_check_patient_exists.return_value = self.patient

        mock_get_segments.return_value = [
            "Segment 1",
            "Segment 2",
            "Segment 3",
            "Segment 4",
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
            "CON Welcome to Uzazi Salama,"
            " please select your preferred language to proceed:"
            "\n1. English\n2. Kiswahili",
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

        # Select "Enroll to Education"
        request_data["data"]["response"] = "1*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Select a Category you would like to enroll to:"
            "\n1. Segment 1\n2. Segment 2\n3. Segment 3\n4. Segment 4",
            response.data["data"]["detail"],
        )

        # Wrong input
        request_data["data"]["response"] = "1*2*5"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Invalid input. "
            "Please enter correct data for confirm_enrollment again.",
            response.data["data"]["detail"],
        )

    @patch(
        "sil_advantage.notifications.ussd.managers.segment_manager.SegmentManager.add_person_to_segment"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.segment_manager.SegmentManager.get_available_segments_for_person"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager.PatientManager.check_patient_exists"
    )
    def test_enroll_to_education_no_segments(
        self, mock_check_patient_exists, mock_get_segments, mock_add_person
    ):
        """Test enrollment for registered patient."""
        mock_check_patient_exists.return_value = self.patient
        mock_get_segments.return_value = []

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
            "CON Welcome to Uzazi Salama,"
            " please select your preferred language to proceed:"
            "\n1. English\n2. Kiswahili",
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
        # Select "Enroll to Education"
        request_data["data"]["response"] = "1*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "END No available programs to enroll in.",
            response.data["data"]["detail"],
        )

    @patch(
        "sil_advantage.notifications.ussd.managers.segment_manager.SegmentManager.add_person_to_segment"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.segment_manager.SegmentManager.get_available_segments_for_person"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager.PatientManager.check_patient_exists"
    )
    def test_view_patient_details(
        self, mock_check_patient_exists, mock_get_segments, mock_add_person
    ):
        """Test enrollment for registered patient."""
        mock_check_patient_exists.return_value = self.patient
        mock_get_segments.return_value = []

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
            "CON Welcome to Uzazi Salama,"
            " please select your preferred language to proceed:"
            "\n1. English\n2. Kiswahili",
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

        # Select "View Details"
        request_data["data"]["response"] = "1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Hello, John, here are your registered details:"
            "\nName: John Doe\nPhone Number: +254712345678\nDate of Birth: 1990-01-01\n"
            "Gender: MALE\n\n0. Back to Main Menu",
            response.data["data"]["detail"],
        )
