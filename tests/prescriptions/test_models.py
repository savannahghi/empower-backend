"""prescrtiion model tests."""
import uuid
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from model_bakery import baker

from sil_advantage.common.models import OrgUnit, Person
from sil_advantage.patients.models import Patient
from sil_advantage.prescriptions.models import (
    DosageInstruction,
    Prescription,
    PrescriptionTransitionLogStatus,
)
from sil_advantage.visits.models import Queue
from tests.common.test_common_views import LoggedInMixin


@pytest.mark.django_db
class TestPrescriptionModel(LoggedInMixin):
    """Test prescription models."""

    def setUp(self):
        """Set up the test environment."""
        super().setUp()
        self.patient = baker.make(
            Patient,
            clinical_id="0e268aad-e5b4-44c0-bb4a-5e0695022559",
        )
        self.org = self.global_organisation
        self.org.tenant_id = uuid.uuid4()
        self.org.save()
        self.orgunit = baker.make(
            OrgUnit,
            organisation=self.org,
            erp_id="f249c5e2-d4b9-4a24-8ce2-83451aeb837e",
        )

    def test_prescription_transition_log(self):
        """Test prescription transition logs."""
        prescription = baker.make(Prescription, status="ACTIVE")
        assert PrescriptionTransitionLogStatus.objects.count() == 0

        prescription.status = "COMPLETED"
        prescription.save()
        assert PrescriptionTransitionLogStatus.objects.count() == 1

    @override_settings(
        SYNC_WITH_CLINICAL_SERVICE=True,
        HEALTH_CRM_API_URL="https://clinical-multitenant-uat.savannahghi.org",
    )
    @patch("sil_advantage.common.api_clients.clinical.Client")
    @patch("sil_advantage.common.api_clients.clinical.get_auth_server_credentials")
    def test_create_medication_request_on_clinical(self, mock_auth, mock_gql_client):
        """Test creating a medication on clinical service."""
        mock_auth.return_value = {"access_token": "P8HmBs8fsNIkTL7ikcntaWtyX3stY2"}
        encounter_id = "d0abd298-5c8c-4fd8-b964-f606cc1b49a8"
        prescription_id = "51e4e9b8-abf6-4a39-aba8-f038a7c6f0d4"
        gql_client = mock_gql_client.return_value

        gql_client.execute.return_value = {
            "createPrescription": {
                "id": prescription_id,
                "encounterID": encounter_id,
                "status": "active",
                "medication": "Amoxicillin",
                "authoredOn": "2024-11-13T09:42:04+03:00",
                "diagnosis": "",
                "facilityName": "Main Branch",
                "orderedBy": "Main Branch",
                "priority": "routine",
                "dosageInstructions": [
                    {
                        "route": "Oral",
                        "doseQuantity": 2.0,
                        "doseUnit": "Capsules",
                        "period": "8",
                        "periodUnit": "h",
                        "frequency": 1,
                        "duration": "5",
                        "durationUnit": "d",
                        "startDate": str(timezone.now().date()),
                        "endDate": str(
                            timezone.now().date() + timezone.timedelta(days=7)
                        ),
                        "condition": "",
                        "patientInstruction": "Take it after meals",
                    }
                ],
            },
        }

        person = baker.make(
            Person,
            first_name="John",
            last_name="Doe",
            gender="MALE",
            date_of_birth="1998-06-14",
            deceased=False,
            organisation=self.org,
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        patient = baker.make(
            Patient,
            person=person,
            organisation=self.org,
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        queue = baker.make(
            Queue, name="Triage", id="d0abd298-5c8c-4fd8-b964-f606cc1b49a8"
        )
        with override_settings(SYNC_WITH_CLINICAL_SERVICE=False):
            prescription = Prescription.objects.create(
                status="ACTIVE",
                medication_name="Amoxicillin",
                organisation=self.org,
                created_by=self.user.id,
                updated_by=self.user.id,
                patient=patient,
                queue=queue,
                branch_id="f249c5e2-d4b9-4a24-8ce2-83451aeb837e",
            )

            today = timezone.now().date()
            DosageInstruction.objects.create(
                route="Oral",
                dose_quantity=2.0,
                dose_unit="Capsules",
                period="8",
                period_unit="h",
                frequency=1,
                duration="5",
                duration_unit="d",
                start_date=str(today),
                end_date=str(today + timezone.timedelta(days=7)),
                condition="After meals",
                patient_instruction="Take it after meals",
                additional_instruction={},
                prescription=prescription,
                created_by=self.user.id,
                updated_by=self.user.id,
                organisation=self.org,
            )

        gql_client.execute.reset_mock()
        prescription.refresh_from_db()

        prescription.save()

        gql_client.execute.assert_called_once()
        payload = gql_client.execute.call_args[1]["variable_values"]

        self.assertEqual(
            payload,
            {
                "input": {
                    "encounterID": encounter_id,
                    "priority": "routine",
                    "medicationName": "Amoxicillin",
                    "dosageInstructions": [
                        {
                            "route": "Oral",
                            "doseQuantity": 2.0,
                            "doseUnit": "Capsules",
                            "period": "8",
                            "periodUnit": "h",
                            "frequency": 1,
                            "duration": "5",
                            "durationUnit": "d",
                            "startDate": str(today),
                            "endDate": str(today + timezone.timedelta(days=7)),
                            "condition": "After meals",
                            "patientInstruction": "Take it after meals",
                            "additionalInstruction": [],
                            "asNeeded": False,
                        }
                    ],
                }
            },
        )

        prescription.refresh_from_db()
        assert str(prescription.medication_request_id) == prescription_id
