"""Clinical Service."""
import logging
import uuid
from typing import Any

from django.conf import settings
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import (
    TransportProtocolError,
    TransportQueryError,
    TransportServerError,
)

from sil_advantage.common.api_clients.auth_server import (
    get_auth_server_credentials,
)

LOGGER = logging.getLogger(__file__)


class ClinicalServiceClient:
    """API Client for the Clinical Service."""

    def __init__(
        self,
        org_id: uuid.UUID,
        facility_id: uuid.UUID,
    ) -> None:
        """Initialize the API Client."""
        credz = get_auth_server_credentials()
        headers = {
            "Authorization": f"Bearer {credz['access_token']}",
            "Clinical-Organization-ID": str(org_id),
            "Clinical-Facility-ID": str(facility_id),
        }
        transport = AIOHTTPTransport(
            url=f"{settings.CLINICAL_SERVICE_URL}/graphql",
            headers=headers,
        )
        self.client = Client(
            transport=transport,
            fetch_schema_from_transport=True,
        )

    def query(self, query_string: str, payload: dict) -> dict[str, Any]:
        """Run a GraphQL query."""
        return self.client.execute(
            gql(query_string),
            variable_values=payload,
        )

    # Patients
    def create_patient(self, payload: dict) -> dict[str, Any]:
        """Create a patient."""
        try:
            return self.query(
                """
                    mutation($input: PatientInput!){
                        createPatient(input: $input){
                            id
                            name
                            phoneNumber
                            gender
                            birthDate
                            active
                        }
                    }
                """,
                payload,
            )["createPatient"]
        except (
            TransportServerError,
            TransportProtocolError,
            TransportQueryError,
        ):
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
            payload["id"] = str(patient_id)
            return self.query(
                """
                    mutation($id: String!, $input: PatchPatientInput!) {
                        patchPatient(id: $id, input: $input) {
                            id
                            name
                            phoneNumber
                            gender
                            birthDate
                            active
                        }
                    }
                """,
                payload,
            )["patchPatient"]
        except (
            TransportServerError,
            TransportProtocolError,
            TransportQueryError,
        ):
            LOGGER.error(
                "Error while updating patient on clinical server",
                exc_info=True,
                extra={"Payload": payload},
            )
            return {"error": "Error while updating patient on clinical server"}

    def delete_patient(self, patient_id: uuid.UUID) -> bool:
        """Delete a patient."""
        try:
            payload = {"id": str(patient_id)}
            return self.query(
                """
                    mutation($id: String!) {
                        deletePatient(id: $id)
                    }
                """,
                payload,
            )["deletePatient"]
        except (
            TransportServerError,
            TransportProtocolError,
            TransportQueryError,
        ):
            LOGGER.error(
                "Error while deleting patient on clinical server",
                exc_info=True,
                extra={"Patient ID": patient_id},
            )
            return False

    # Visits
    def create_visit(self, payload: dict) -> dict[str, Any]:
        """Create a visit."""
        try:
            return self.query(
                """
                    mutation($episodeOfCare: EpisodeOfCareInput!){
                        createEpisodeOfCare(episodeOfCare: $episodeOfCare) {
                            id
                            status
                            patientID
                        }
                    }
                """,
                payload,
            )["createEpisodeOfCare"]
        except (
            TransportServerError,
            TransportProtocolError,
            TransportQueryError,
        ):
            LOGGER.error(
                "Error while creating visit on clinical server",
                exc_info=True,
                extra={"Payload": payload},
            )
            return {"error": "Error while creating visit on clinical server"}

    def update_visit(
        self,
        visit_id: uuid.UUID,
        payload: dict,
    ) -> dict[str, Any]:
        """Update a visit."""
        try:
            payload["id"] = str(visit_id)
            return self.query(
                """
                    mutation($id: String!, $episodeOfCare: EpisodeOfCareInput!){
                        patchEpisodeOfCare(id: $id, episodeOfCare: $episodeOfCare) {
                            id
                            status
                            patientID
                        }
                    }
                """,
                payload,
            )["patchEpisodeOfCare"]
        except (
            TransportServerError,
            TransportProtocolError,
            TransportQueryError,
        ):
            LOGGER.error(
                "Error while updating visit on clinical server",
                exc_info=True,
                extra={"Payload": payload},
            )
            return {"error": "Error while updating visit on clinical server"}

    # Encounters
    def create_encounter(self, payload: dict) -> dict[str, Any]:
        """Create an encounter."""
        try:
            response = self.query(
                """
                    mutation($episodeID: String!) {
                        startEncounter(episodeID: $episodeID)
                    }
                """,
                payload,
            )
            return {"id": response["startEncounter"]}
        except (
            TransportServerError,
            TransportProtocolError,
            TransportQueryError,
        ):
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
            payload["encounterID"] = str(encounter_id)
            return self.query(
                """
                    mutation ($encounterID: String!, $input: EncounterInput!){
                        patchEncounter(encounterID: $encounterID, input: $input) {
                            id
                            status
                        }
                    }
                """,
                payload,
            )["patchEncounter"]
        except (
            TransportServerError,
            TransportProtocolError,
            TransportQueryError,
        ):
            LOGGER.error(
                "Error while updating encounter on clinical server",
                exc_info=True,
                extra={"Payload": payload},
            )
            return {"error": "Error while updating encounter on clinical server"}

    # MedicationRequests
    def create_prescription(self, payload: dict) -> dict[str, Any]:
        """Create a medication request."""
        try:
            return self.query(
                """
                    mutation ($input: PrescriptionInput!) {
                        createPrescription(input: $input) {
                            id
                            encounterID
                            status
                            medication
                            authoredOn
                            diagnosis
                            facilityName
                            orderedBy
                            dosageInstructions {
                                route
                                doseQuantity
                                doseUnit
                                period
                                periodUnit
                                frequency
                                duration
                                durationUnit
                                startDate
                                endDate
                                condition
                                patientInstruction
                            }
                        }
                    }
                """,
                payload,
            )["createPrescription"]
        except (
            TransportServerError,
            TransportProtocolError,
            TransportQueryError,
        ):
            LOGGER.error(
                "Error while creating medication request on clinical server",
                exc_info=True,
                extra={"Payload": payload},
            )
            return {
                "error": "Error while creating medication request on clinical server"
            }
