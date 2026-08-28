"""USSD registration views."""
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
    def test_kiswahili_flow(self, mock_create_patient, mock_get_available_regions):
        """Test Kiswahili registration flow."""
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
            "CON Welcome to Uzazi Salama, please select your preferred "
            "language to proceed:\n1. English\n2. Kiswahili",
            response.data["data"]["detail"],
        )

        # Select Kiswahili language
        request_data["data"]["response"] = "2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Tafadhali chagua huduma:\n1. Jisajili\n2. Badilisha Lugha",
            response.data["data"]["detail"],
        )

        # Invalid Selection
        request_data["data"]["response"] = "2*3"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Tafadhali chagua huduma:\n1. Jisajili\n2. Badilisha Lugha",
            response.data["data"]["detail"],
        )

        # Select "Jisajili"
        request_data["data"]["response"] = "2*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Chagua eneo lako:\n1. Kilifi North\n2. Kilifi South"
            "\n0. Rudi kwenye Menyu Kuu",
            response.data["data"]["detail"],
        )
        request_data["data"]["response"] = "2*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Kujisajili, tafadhali ingiza jina lako la "
            "kwanza na la mwisho (Mfano Jane Kaberu):",
            response.data["data"]["detail"],
        )

        # Enter name
        request_data["data"]["response"] = "2*1*1*John Doe"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Weka Tarehe ya Kuzaliwa (DD/MM/YYYY):",
            response.data["data"]["detail"],
        )

        # Enter Date of Birth
        request_data["data"]["response"] = "2*1*1*John Doe*01/01/1990"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Chagua Jinsia:\n1. Mwanaume\n2. Mwanamke\n3. Nyingine\n",
            response.data["data"]["detail"],
        )
        # Select Gender
        request_data["data"]["response"] = "2*1*1*John Doe*01/01/1990*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Hakikisha usajili kwenye programu ya uzazi salama:\n"
            "Jina: John Doe\n"
            "Tarehe ya Kuzaliwa: 01/01/1990\n"
            "Jinsia: Mwanamume\n\n"
            "1. Thibitisha\n2. Ghairi",
            response.data["data"]["detail"],
        )
        # Validate the consent selection
        request_data["data"]["response"] = "2*1*1*John Doe*01/01/1990*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Ungependa Kupokea SMS kutoka Uzazi Salama? "
            "Chagua 1 kukubali au 2 kukataa:\n"
            "1. Ndio\n"
            "2. Hapana",
            response.data["data"]["detail"],
        )
        # Confirm Registration
        request_data["data"]["response"] = "2*1*1*John Doe*01/01/1990*1*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "END Asante kwa kujisajili na Programu ya Uzazi Salama."
            "Utapokea ujumbe mfupi wa maandishi wa uthibitisho hivi karibuni.",
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
            language="sw",
        )

    @patch(
        "sil_advantage.notifications.ussd.managers.operation_region_manager.RegionManager.get_operating_regions"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager."
        "PatientManager.create_patient"
    )
    def test_cancel_registration_kiswahili(
        self, mock_create_patient, mock_get_available_regions
    ):
        """Test cancel registration."""
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
            "CON Welcome to Uzazi Salama, please select your preferred "
            "language to proceed:\n1. English\n2. Kiswahili",
            response.data["data"]["detail"],
        )

        # Select Kiswahili language
        request_data["data"]["response"] = "2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Tafadhali chagua huduma:\n1. Jisajili\n2. Badilisha Lugha",
            response.data["data"]["detail"],
        )

        # Select "Jisajili"
        request_data["data"]["response"] = "2*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Chagua eneo lako:\n1. Kilifi North\n2. Kilifi South"
            "\n0. Rudi kwenye Menyu Kuu",
            response.data["data"]["detail"],
        )
        request_data["data"]["response"] = "2*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Kujisajili, tafadhali ingiza jina lako la "
            "kwanza na la mwisho (Mfano Jane Kaberu):\n0. Rudi kwenye Menyu Kuu",
            response.data["data"]["detail"],
        )

        # Enter name
        request_data["data"]["response"] = "2*1*1*John Doe"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Weka Tarehe ya Kuzaliwa (DD/MM/YYYY):\n0. Rudi kwenye Menyu Kuu",
            response.data["data"]["detail"],
        )

        # Enter Date of Birth
        request_data["data"]["response"] = "2*1*1*John Doe*01/01/1990"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Chagua Jinsia:\n1. Mwanaume\n2. Mwanamke\n3. Nyingine\n",
            response.data["data"]["detail"],
        )

        # Select Gender
        request_data["data"]["response"] = "2*1*1*John Doe*01/01/1990*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Hakikisha usajili kwenye programu ya uzazi salama:\n"
            "Jina: John Doe\n"
            "Tarehe ya Kuzaliwa: 01/01/1990\n"
            "Jinsia: Mwanamume\n\n"
            "1. Thibitisha\n2. Ghairi\n0. Rudi kwenye Menyu Kuu",
            response.data["data"]["detail"],
        )

        # Cancel Registration - swahili
        request_data["data"]["response"] = "2*1*1*John Doe*01/01/1990*1*2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("END Usajili umeghairiwa.", response.data["data"]["detail"])
        mock_create_patient.assert_not_called()

    @patch(
        "sil_advantage.notifications.ussd.managers.operation_region_manager.RegionManager.get_operating_regions"
    )
    @patch(
        "sil_advantage.notifications.ussd.managers.patient_manager."
        "PatientManager.create_patient"
    )
    def test_registration_failure_kiswahili(
        self, mock_create_patient, mock_get_available_regions
    ):
        """Test registration failure scenario in Kiswahili."""
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
            "CON Welcome to Uzazi Salama, please select your "
            "preferred language to proceed:\n1. English\n2. Kiswahili",
            response.data["data"]["detail"],
        )

        # Select Kiswahili language
        request_data["data"]["response"] = "2"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Tafadhali chagua huduma:\n1. Jisajili\n2. Badilisha Lugha",
            response.data["data"]["detail"],
        )

        # Select "Jisajili"
        request_data["data"]["response"] = "2*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Chagua eneo lako:\n1. Kilifi North\n2. Kilifi South"
            "\n0. Rudi kwenye Menyu Kuu",
            response.data["data"]["detail"],
        )
        request_data["data"]["response"] = "2*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Kujisajili, tafadhali ingiza jina lako la "
            "kwanza na la mwisho (Mfano Jane Kaberu):\n0. Rudi kwenye Menyu Kuu",
            response.data["data"]["detail"],
        )

        # Enter name
        request_data["data"]["response"] = "2*1*1*John Doe"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Weka Tarehe ya Kuzaliwa (DD/MM/YYYY):\n0. Rudi kwenye Menyu Kuu",
            response.data["data"]["detail"],
        )

        # Enter Date of Birth
        request_data["data"]["response"] = "2*1*1*John Doe*01/01/1990"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Chagua Jinsia:\n1. Mwanaume\n2. Mwanamke\n3. Nyingine\n",
            response.data["data"]["detail"],
        )

        # Select Gender
        request_data["data"]["response"] = "2*1*1*John Doe*01/01/1990*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Hakikisha usajili kwenye programu ya uzazi salama:\n"
            "Jina: John Doe\n"
            "Tarehe ya Kuzaliwa: 01/01/1990\n"
            "Jinsia: Mwanamume\n\n"
            "1. Thibitisha\n2. Ghairi\n0. Rudi kwenye Menyu Kuu",
            response.data["data"]["detail"],
        )

        # Validate the consent selection
        request_data["data"]["response"] = "2*1*1*John Doe*01/01/1990*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "CON Ungependa Kupokea SMS kutoka Uzazi Salama? "
            "Chagua 1 kukubali au 2 kukataa:\n"
            "1. Ndio\n"
            "2. Hapana\n0.Rudi kwenye Menyu Kuu",
            response.data["data"]["detail"],
        )

        # Confirm Registration
        request_data["data"]["response"] = "2*1*1*John Doe*01/01/1990*1*1*1"
        response = self.client.post(url, request_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            "END Usajili umekuwa na hitilafu. Tafadhali jaribu tena.",
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
            language="sw",
        )
