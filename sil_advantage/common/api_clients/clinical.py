"""Clinical Service."""
import logging
import uuid
from typing import Any, Optional

import requests
from django.conf import settings

from sil_advantage.sil_auth.keycloak import service_account_token

LOGGER = logging.getLogger(__file__)

TIMEOUT = 30


class ClinicalServiceClient:
    """API Client for the Clinical Service.

    Clinical exposes the same operations over REST and GraphQL. REST is the
    surface under active development, and it does not validate identifier types
    against a generated enum, so it tolerates the older names this version
    sends.
    """

    def __init__(
        self,
        org_id: uuid.UUID,
        facility_id: uuid.UUID,
    ) -> None:
        """Initialize the API Client."""
        self.base_url = str(settings.CLINICAL_SERVICE_URL).rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {service_account_token()}",
            "Clinical-Organization-ID": str(org_id),
            "Clinical-Facility-ID": str(facility_id),
        }

    def request(
        self,
        method: str,
        path: str,
        payload: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Send a request to the clinical service."""
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            json=payload,
            headers=self.headers,
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        return response.json() if response.content else {}

    # Patients
    def create_patient(self, payload: dict) -> dict[str, Any]:
        """Create a patient."""
        try:
            return self.request("POST", "/api/v1/patient", payload["input"])
        except requests.RequestException:
            LOGGER.error(
                "Error while creating patient on clinical server",
                exc_info=True,
                extra={"Payload": payload},
            )
            return {"error": "Error while creating patient on clinical server"}

    def update_patient(
        self,
        patient_id: uuid.UUID,
        payload: dict,
    ) -> dict[str, Any]:
        """Update a patient."""
        try:
            return self.request(
                "PATCH",
                f"/api/v1/patient/{patient_id}",
                payload["input"],
            )
        except requests.RequestException:
            LOGGER.error(
                "Error while updating patient on clinical server",
                exc_info=True,
                extra={"Payload": payload},
            )
            return {"error": "Error while updating patient on clinical server"}

    def delete_patient(self, patient_id: uuid.UUID) -> bool:
        """Delete a patient."""
        try:
            self.request("DELETE", f"/api/v1/patient/{patient_id}")
            return True
        except requests.RequestException:
            LOGGER.error(
                "Error while deleting patient on clinical server",
                exc_info=True,
                extra={"Patient ID": patient_id},
            )
            return False

    # Visits
    def create_visit(self, payload: dict) -> dict[str, Any]:
        """Create a visit, which clinical models as an episode of care."""
        try:
            return self.request(
                "POST",
                "/api/v1/episode-of-care",
                payload["episodeOfCare"],
            )
        except requests.RequestException:
            LOGGER.error(
                "Error while creating visit on clinical server",
                exc_info=True,
                extra={"Payload": payload},
            )
            return {"error": "Error while creating visit on clinical server"}

    def update_visit(
        self,
        episode_of_care_id: uuid.UUID,
        payload: dict,
    ) -> dict[str, Any]:
        """Update a visit."""
        try:
            return self.request(
                "PATCH",
                f"/api/v1/episode-of-care/{episode_of_care_id}",
                payload["episodeOfCare"],
            )
        except requests.RequestException:
            LOGGER.error(
                "Error while updating visit on clinical server",
                exc_info=True,
                extra={"Payload": payload},
            )
            return {"error": "Error while updating visit on clinical server"}

    # Encounters
    def create_encounter(self, payload: dict) -> dict[str, Any]:
        """Start an encounter on an episode of care."""
        try:
            response = self.request(
                "POST",
                "/api/v1/encounter",
                {"episodeOfCareID": payload["episodeID"]},
            )
            # This endpoint returns the new id under `results`.
            return {"id": response["results"]}
        except (requests.RequestException, KeyError):
            LOGGER.error(
                "Error while creating encounter on clinical server",
                exc_info=True,
                extra={"Payload": payload},
            )
            return {"error": "Error while creating encounter on clinical server"}

    def update_encounter(
        self,
        encounter_id: uuid.UUID,
        payload: dict,
    ) -> dict[str, Any]:
        """Update an encounter."""
        try:
            return self.request(
                "PATCH",
                f"/api/v1/encounter/{encounter_id}",
                payload["input"],
            )
        except requests.RequestException:
            LOGGER.error(
                "Error while updating encounter on clinical server",
                exc_info=True,
                extra={"Payload": payload},
            )
            return {
                "error": "Error while updating encounter on clinical server"
            }

    # Prescriptions
    def create_prescription(self, payload: dict) -> dict[str, Any]:
        """Create a prescription."""
        try:
            return self.request(
                "POST",
                "/api/v1/medication/prescription",
                payload["input"],
            )
        except requests.RequestException:
            LOGGER.error(
                "Error while creating prescription on clinical server",
                exc_info=True,
                extra={"Payload": payload},
            )
            return {
                "error": "Error while creating prescription on clinical server"
            }
