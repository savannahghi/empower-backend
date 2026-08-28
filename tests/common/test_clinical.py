"""Test API Client for the Clinical Service."""

import unittest
from unittest.mock import patch

from gql.transport.exceptions import (
    TransportProtocolError,
    TransportQueryError,
    TransportServerError,
)

from sil_advantage.common.api_clients.clinical import ClinicalServiceClient


class TestClinicalServiceClient(unittest.TestCase):
    """Testing API Client for the Clinical Service."""

    @patch("sil_advantage.common.api_clients.clinical.get_auth_server_credentials")
    def setUp(self, mock_get_auth_server_credentials):
        """Set up the test environment."""
        mock_get_auth_server_credentials.return_value = {
            "access_token": "P8HmBs8fsNIkTL7ikcntaWtyX3stY2"
        }
        self.client = ClinicalServiceClient(
            org_id="ebef581c-494b-4772-9e49-0b0755c44e61",
            facility_id="bda9242c-c579-4102-828a-a5476a38e74d",
        )

    def test_create_patient(self):
        """Test create a patient on clinical server."""
        payload = {
            "name": "John Doe",
            "phoneNumber": "+254790360360",
            "gender": "male",
            "birthDate": "1990-01-01",
            "active": True,
        }
        with patch.object(self.client, "query") as mock_query:
            mock_query.side_effect = (
                TransportServerError("Server Error Message"),
                TransportProtocolError("Protocol Error Message"),
                TransportQueryError("Query Error Message"),
            )
            response_after_error = self.client.create_patient(payload)
            self.assertEqual(
                response_after_error,
                {"error": "Error while creating patient on clinical server"},
            )

    def test_update_patient(self):
        """Test update a patient on clinical server."""
        patient_id = "bda9242c-c579-4102-828a-a5476a38e743"
        payload = {
            "name": "John Doe",
            "phoneNumber": "+254790360360",
            "gender": "male",
            "birthDate": "1990-01-01",
            "active": True,
        }
        with patch.object(self.client, "query") as mock_query:
            mock_query.side_effect = (
                TransportServerError("Server Error Message"),
                TransportProtocolError("Protocol Error Message"),
                TransportQueryError("Query Error Message"),
            )
            response_after_error = self.client.update_patient(patient_id, payload)
            self.assertEqual(
                response_after_error,
                {"error": "Error while updating patient on clinical server"},
            )

    def test_delete_patient(self):
        """Test delete a patient on clinical server."""
        patient_id = "bda9242c-c579-4102-828a-a5476a38e743"
        with patch.object(self.client, "query") as mock_query:
            mock_query.side_effect = (
                TransportServerError("Server Error Message"),
                TransportProtocolError("Protocol Error Message"),
                TransportQueryError("Query Error Message"),
            )
            response_after_error = self.client.delete_patient(patient_id)
            self.assertEqual(response_after_error, False)

    def test_create_visit(self):
        """Test Create a visit on clinical server."""
        visit_id = "d728a5c8-52fa-4b53-9e56-77c9527d7e14"
        episode_id = "bc0343b3-bf57-4ba9-ab8f-485459c9c2e1"
        patient_id = "bc0343b3-bf57-4ba9-ab8f-485459c9c2e0"
        payload = {
            "id": visit_id,
            "episodeOfCare": {
                "id": episode_id,
                "status": "completed",
                "patientID": patient_id,
            },
        }
        with patch.object(self.client, "query") as mock_query:
            mock_query.side_effect = (
                TransportServerError("Server Error Message"),
                TransportProtocolError("Protocol Error Message"),
                TransportQueryError("Query Error Message"),
            )
            response_after_error = self.client.create_visit(payload)
            self.assertEqual(
                response_after_error,
                {"error": "Error while creating visit on clinical server"},
            )

    def test_update_visit(self):
        """Test Update a visit on clinical server."""
        visit_id = "d728a5c8-52fa-4b53-9e56-77c9527d7e14"
        episode_id = "bc0343b3-bf57-4ba9-ab8f-485459c9c2e1"
        patient_id = "bc0343b3-bf57-4ba9-ab8f-485459c9c2e0"
        payload = {
            "id": visit_id,
            "episodeOfCare": {
                "id": episode_id,
                "status": "completed",
                "patientID": patient_id,
            },
        }
        with patch.object(self.client, "query") as mock_query:
            mock_query.side_effect = (
                TransportServerError("Server Error Message"),
                TransportProtocolError("Protocol Error Message"),
                TransportQueryError("Query Error Message"),
            )
            response_after_error = self.client.update_visit(visit_id, payload)
            self.assertEqual(
                response_after_error,
                {"error": "Error while updating visit on clinical server"},
            )

    def test_create_encounter(self):
        """Test Create an encounter on clinical server."""
        episode_id = "bc0343b3-bf57-4ba9-ab8f-485459c9c2e1"
        payload = {"episodeID": episode_id}
        with patch.object(self.client, "query") as mock_query:
            mock_query.side_effect = (
                TransportServerError("Server Error Message"),
                TransportProtocolError("Protocol Error Message"),
                TransportQueryError("Query Error Message"),
            )
            response_after_error = self.client.create_encounter(payload)
            self.assertEqual(
                response_after_error,
                {"error": "Error while creating encounter on clinical server"},
            )

    def test_update_encounter(self):
        """Test Update an encounter on clinical server."""
        encounter_id = "bc0343b3-bf57-4ba9-ab8f-485459c9c2eb"
        payload = {
            "encounterID": "bc0343b3-bf57-4ba9-ab8f-485459c9c2eb",
            "input": {
                "id": "bc0343b3-bf57-4ba9-ab8f-485459c9c2eb",
                "status": "completed",
            },
        }
        with patch.object(self.client, "query") as mock_query:
            mock_query.side_effect = (
                TransportServerError("Server Error Message"),
                TransportProtocolError("Protocol Error Message"),
                TransportQueryError("Query Error Message"),
            )
            response_after_error = self.client.update_encounter(encounter_id, payload)
            self.assertEqual(
                response_after_error,
                {"error": "Error while updating encounter on clinical server"},
            )

    def test_create_prescription(self):
        """Test creating a prescription."""
        encounter_id = "bc0343b3-bf57-4ba9-ab8f-485459c9c2eb"
        payload = {
            "encounterID": encounter_id,
            "priority": "routine",
            "medicationName": "Amoxicillin",
            "dosageInstructions": [
                {
                    "route": "Oral",
                    "doseQuantity": 2,
                    "doseUnit": "Capsules",
                    "period": "8",
                    "periodUnit": "h",
                    "frequency": 1,
                    "duration": "5",
                    "durationUnit": "d",
                    "startDate": "2024-11-11",
                    "endDate": "2024-11-18",
                    "condition": "After meals",
                    "patientInstruction": "Take it after meals",
                    "additionalInstruction": [""],
                    "asNeeded": False,
                    "freeTextInstruction": "",
                }
            ],
        }
        with patch.object(self.client, "query") as mock_query:
            mock_query.side_effect = (
                TransportServerError("Server Error Message"),
                TransportProtocolError("Protocol Error Message"),
                TransportQueryError("Query Error Message"),
            )
            response_after_error = self.client.create_prescription(payload)
            self.assertEqual(
                response_after_error,
                {"error": "Error while creating medication request on clinical server"},
            )
