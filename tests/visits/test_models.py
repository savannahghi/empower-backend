"""Test visits models."""

import re
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone
from model_bakery import baker

from sil_advantage.common.models import OrgUnit
from sil_advantage.patients.models import Patient
from sil_advantage.visits.models import Queue, ServiceRequest, Visit
from tests.common.test_common_views import LoggedInMixin


class VisitModelTestCase(LoggedInMixin):
    """Test Visit model."""

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
        baker.make(
            OrgUnit,
            organisation=self.org,
            erp_id="f249c5e2-d4b9-4a24-8ce2-83451aeb837e",
        )

    def test_start_before_end_validation(self):
        """Test that visit start is before visit end."""
        visit = baker.make(Visit, status="ARRIVED")

        expected_error = re.escape(
            "{'end': ['The visit end must be greater than its start.']}"
        )
        with pytest.raises(ValidationError, match=expected_error):
            visit.end = timezone.now() - timezone.timedelta(days=3)
            visit.save()

    def test_logging_queue_transitions(self):
        """Test logging queue transitions."""
        visit = baker.make(Visit, status="ARRIVED")
        triage_queue = baker.make(Queue, name="Triage")
        consultation_queue = baker.make(Queue, name="Consultation Room 1")

        assert list(visit.queue_transition_logs.all()) == []

        # None -> Triage
        visit.current_queue = triage_queue
        visit.save()
        assert visit.queue_transition_logs.count() == 1
        log = visit.queue_transition_logs.latest("created")
        assert log.source is None
        assert log.source_queue_name == "None"
        assert log.destination == triage_queue
        assert log.destination_queue_name == "Triage"
        srq_triage = ServiceRequest.objects.latest("created")
        assert srq_triage.previous_queue_name == "None"

        # Triage -> Consultation
        visit.current_queue = consultation_queue
        visit.save()
        assert visit.queue_transition_logs.count() == 2
        log = visit.queue_transition_logs.latest("created")
        assert log.source == triage_queue
        assert log.destination == consultation_queue
        srq_cons = ServiceRequest.objects.latest("created")
        assert srq_cons.previous_queue_name == "Triage"
        assert srq_triage.previous_queue_name == "None"

        # No change
        visit.current_queue = consultation_queue
        visit.save()
        assert visit.queue_transition_logs.count() == 2

        # Consultation -> None
        visit.current_queue = None
        visit.save()
        assert visit.queue_transition_logs.count() == 3
        log = visit.queue_transition_logs.latest("created")
        assert log.source == consultation_queue
        assert log.source_queue_name == "Consultation Room 1"
        assert log.destination is None
        assert log.destination_queue_name == "None"

    def test_visit_status_transition_on_credit_visit(self):
        """Test logging queue transitions."""
        visit_credit = baker.make(Visit, billing_class="CREDIT", status="ARRIVED")
        visit_cash = baker.make(Visit, billing_class="CASH", status="ARRIVED")
        triage_queue = baker.make(Queue, name="Triage")
        consultation_queue = baker.make(Queue, name="Consultation Room 1")

        # None -> Triage
        visit_credit.current_queue = triage_queue
        visit_cash.current_queue = triage_queue
        visit_credit.save()
        assert visit_cash.status == "ARRIVED"
        assert visit_credit.status == "ARRIVED"

        # Triage -> Consultation
        visit_credit.current_queue = consultation_queue
        visit_cash.current_queue = consultation_queue
        visit_credit.save()
        visit_cash.save()
        assert visit_credit.status == "IN_PROGRESS"
        assert visit_cash.status == "ARRIVED"

    def test_validate_only_one_visit_open(self):
        """Test validating one visit open per patient."""
        patient = baker.make(Patient)
        baker.make(Visit, patient=patient, status="IN_PROGRESS")

        expected_message = re.escape(
            "{'__all__': [\"Please close the patient's 1 open visit(s) "
            'before opening a new one."]}'
        )
        with pytest.raises(ValidationError, match=expected_message):
            baker.make(Visit, patient=patient, status="ARRIVED")

    @override_settings(
        SYNC_WITH_CLINICAL_SERVICE=True,
        HEALTH_CRM_API_URL="https://clinical-multitenant-uat.savannahghi.org",
    )
    @patch("sil_advantage.common.api_clients.clinical.Client")
    @patch("sil_advantage.common.api_clients.clinical.get_auth_server_credentials")
    def test_sync_with_clinical_service_on_save(self, mock_auth, mock_gql_client):
        """Test visit sync with the clinical service."""
        mock_auth.return_value = {
            "access_token": "P8HmBs8fsNIkTL7ikcntaWtyX3stY2",
        }
        episode_id = "bc0343b3-bf57-4ba9-ab8f-485459c9c2eb"
        gql_client = mock_gql_client.return_value
        gql_client.execute.return_value = {
            "createEpisodeOfCare": {
                "id": episode_id,
                "status": "active",
                "patientID": "0e268aad-e5b4-44c0-bb4a-5e0695022559",
            },
            "patchEpisodeOfCare": {
                "id": episode_id,
                "status": "cancelled",
                "patientID": "0e268aad-e5b4-44c0-bb4a-5e0695022559",
            },
        }

        # Test Create
        visit = baker.make(
            Visit,
            patient=self.patient,
            status="ARRIVED",
            organisation=self.org,
            branch_id="f249c5e2-d4b9-4a24-8ce2-83451aeb837e",
        )

        gql_client.execute.assert_called_once()
        payload = gql_client.execute.call_args[1]["variable_values"]
        self.assertEqual(
            payload,
            {
                "episodeOfCare": {
                    "status": "active",
                    "patientID": "0e268aad-e5b4-44c0-bb4a-5e0695022559",
                }
            },
        )
        visit.refresh_from_db()
        assert str(visit.episode_of_care_id) == episode_id

        # Test Update
        gql_client.reset_mock()

        visit.status = "CANCELLED"
        visit.save()

        gql_client.execute.assert_called_once()
        payload = gql_client.execute.call_args[1]["variable_values"]
        self.assertEqual(
            payload,
            {
                "id": episode_id,
                "episodeOfCare": {
                    "status": "cancelled",
                    "patientID": "0e268aad-e5b4-44c0-bb4a-5e0695022559",
                },
            },
        )


class ServiceRequestModelTestCase(LoggedInMixin):
    """Test ServiceRequest model."""

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
        baker.make(
            OrgUnit,
            organisation=self.org,
            erp_id="f249c5e2-d4b9-4a24-8ce2-83451aeb837e",
        )
        self.visit = baker.make(
            Visit,
            patient=self.patient,
            status="ARRIVED",
            episode_of_care_id="bc0343b3-bf57-4ba9-ab8f-485459c9c2eb",
            organisation=self.org,
            branch_id="f249c5e2-d4b9-4a24-8ce2-83451aeb837e",
            start=datetime.now(),
            customer_id="619a9bb1-1f8b-4ace-baf5-e7603de17362",
            guarantor_id="e93a5640-37c2-42e1-8d6f-6e9ff310afe6",
        )

    @override_settings(
        SYNC_WITH_CLINICAL_SERVICE=True,
        HEALTH_CRM_API_URL="https://clinical-multitenant-uat.savannahghi.org",
    )
    @patch("sil_advantage.common.api_clients.clinical.Client")
    @patch("sil_advantage.common.api_clients.clinical.get_auth_server_credentials")
    def test_sync_with_clinical_service_on_save(self, mock_auth, mock_gql_client):
        """Test encounter sync with the clinical service."""
        mock_auth.return_value = {
            "access_token": "P8HmBs8fsNIkTL7ikcntaWtyX3stY2",
        }
        encounter_id = "7e622092-223b-4402-b068-ae42e3eda35a"
        gql_client = mock_gql_client.return_value
        gql_client.execute.return_value = {
            "startEncounter": encounter_id,
            "patchEncounter": {
                "id": encounter_id,
                "status": "finished",
            },
        }

        # Test Create
        srq = baker.make(
            ServiceRequest,
            created=datetime.now(),
            visit=self.visit,
            status="PENDING",
            organisation=self.org,
            branch_id="f249c5e2-d4b9-4a24-8ce2-83451aeb837e",
        )
        gql_client.execute.assert_called_once()
        payload = gql_client.execute.call_args[1]["variable_values"]
        self.assertEqual(
            payload,
            {
                "episodeID": "bc0343b3-bf57-4ba9-ab8f-485459c9c2eb",
            },
        )
        srq.refresh_from_db()
        assert str(srq.encounter_id) == encounter_id

        # Test Updates
        srq.status = "IN_PROGRESS"
        srq.save()

        gql_client.reset_mock()
        srq.status = "ENTERED_IN_ERROR"
        srq.save()

        gql_client.execute.assert_called_once()
        payload = gql_client.execute.call_args[1]["variable_values"]
        self.assertEqual(
            payload,
            {
                "encounterID": str(encounter_id),
                "input": {
                    "status": "finished",
                },
            },
        )

        # Test initial create for existing
        gql_client.reset_mock()

        srq.encounter_id = None
        srq.save()

        gql_client.execute.assert_called_once()
        payload = gql_client.execute.call_args[1]["variable_values"]
        self.assertEqual(
            payload,
            {
                "episodeID": "bc0343b3-bf57-4ba9-ab8f-485459c9c2eb",
            },
        )
