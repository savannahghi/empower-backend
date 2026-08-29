"""Test API Client for the Clinical Service."""

import unittest
from unittest.mock import patch

import requests

from sil_advantage.common.api_clients.clinical import ClinicalServiceClient

PATIENT_ID = "ebef581c-494b-4772-9e49-0b0755c44e61"


class TestClinicalServiceClient(unittest.TestCase):
    """Testing API Client for the Clinical Service."""

    @patch("sil_advantage.common.api_clients.clinical.service_account_token")
    def setUp(self, mock_token):
        """Set up the test environment."""
        mock_token.return_value = "P8HmBs8fsNIkTL7ikcntaWtyX3stY2"
        self.client = ClinicalServiceClient(
            org_id="ebef581c-494b-4772-9e49-0b0755c44e61",
            facility_id="bda9242c-c579-4102-828a-a5476a38e74d",
        )

    def test_operations_send_the_expected_request(self):
        """Each operation maps onto its REST endpoint."""
        cases = [
            (
                lambda: self.client.create_patient({"input": {"a": 1}}),
                ("POST", "/api/v1/patient", {"a": 1}),
            ),
            (
                lambda: self.client.update_patient(PATIENT_ID, {"input": {"a": 1}}),
                ("PATCH", f"/api/v1/patient/{PATIENT_ID}", {"a": 1}),
            ),
            (
                lambda: self.client.create_visit({"episodeOfCare": {"a": 1}}),
                ("POST", "/api/v1/episode-of-care", {"a": 1}),
            ),
            (
                lambda: self.client.update_visit(
                    PATIENT_ID, {"episodeOfCare": {"a": 1}}
                ),
                ("PATCH", f"/api/v1/episode-of-care/{PATIENT_ID}", {"a": 1}),
            ),
            (
                lambda: self.client.update_encounter(
                    PATIENT_ID, {"input": {"a": 1}}
                ),
                ("PATCH", f"/api/v1/encounter/{PATIENT_ID}", {"a": 1}),
            ),
            (
                lambda: self.client.create_prescription({"input": {"a": 1}}),
                ("POST", "/api/v1/medication/prescription", {"a": 1}),
            ),
        ]

        for operation, expected in cases:
            with self.subTest(expected=expected):
                with patch.object(self.client, "request") as mock_request:
                    mock_request.return_value = {"id": PATIENT_ID}
                    operation()
                    mock_request.assert_called_once_with(*expected)

    def test_create_encounter_reads_the_id_from_results(self):
        """The encounter endpoint returns its new id under `results`."""
        with patch.object(self.client, "request") as mock_request:
            mock_request.return_value = {"results": PATIENT_ID}
            response = self.client.create_encounter({"episodeID": "eoc-1"})

        mock_request.assert_called_once_with(
            "POST", "/api/v1/encounter", {"episodeOfCareID": "eoc-1"}
        )
        self.assertEqual(response, {"id": PATIENT_ID})

    def test_delete_patient(self):
        """Deleting reports success as a boolean."""
        with patch.object(self.client, "request") as mock_request:
            mock_request.return_value = {}
            self.assertTrue(self.client.delete_patient(PATIENT_ID))

        with patch.object(self.client, "request") as mock_request:
            mock_request.side_effect = requests.RequestException("boom")
            self.assertFalse(self.client.delete_patient(PATIENT_ID))

    def test_a_failed_request_is_reported_not_raised(self):
        """A transport failure returns an error rather than propagating."""
        cases = [
            (
                lambda: self.client.create_patient({"input": {}}),
                "Error while creating patient on clinical server",
            ),
            (
                lambda: self.client.update_patient(PATIENT_ID, {"input": {}}),
                "Error while updating patient on clinical server",
            ),
            (
                lambda: self.client.create_visit({"episodeOfCare": {}}),
                "Error while creating visit on clinical server",
            ),
            (
                lambda: self.client.update_visit(PATIENT_ID, {"episodeOfCare": {}}),
                "Error while updating visit on clinical server",
            ),
            (
                lambda: self.client.create_encounter({"episodeID": "eoc-1"}),
                "Error while creating encounter on clinical server",
            ),
            (
                lambda: self.client.update_encounter(PATIENT_ID, {"input": {}}),
                "Error while updating encounter on clinical server",
            ),
            (
                lambda: self.client.create_prescription({"input": {}}),
                "Error while creating prescription on clinical server",
            ),
        ]

        for operation, message in cases:
            with self.subTest(message=message):
                with patch.object(self.client, "request") as mock_request:
                    mock_request.side_effect = requests.RequestException("boom")
                    self.assertEqual(operation(), {"error": message})
