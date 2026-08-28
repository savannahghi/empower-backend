"""Test for the prescription views."""
import uuid
from datetime import datetime, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker
from rest_framework import status

from sil_advantage.common.models import Person
from sil_advantage.patients.models import Patient
from sil_advantage.prescriptions.models import Prescription
from sil_advantage.sil_auth.models import SILUser
from sil_advantage.visits.models import Queue
from tests.common.test_common_views import LoggedInMixin

pytestmark = pytest.mark.django_db


class PrescriptionViewsetTestCase(LoggedInMixin):
    """Test Prescription viewset."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        baker.make(SILUser, email="network.admin@slade360.co.ke")

        self.person = baker.make(
            Person,
            first_name="Same",
            last_name="Tabman",
            organisation=self.global_organisation,
        )
        self.patient = baker.make(
            Patient,
            person=self.person,
            organisation=self.global_organisation,
            clinical_id=str(uuid.uuid4()),
        )
        self.headers = {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }
        self.workstation_data = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }
        self.queue = baker.make(Queue, name="Consultation")

    def test_create_prescription(self):
        """Test creating a prescription."""
        start_date = datetime.now().date()

        data = {
            "patient": str(self.patient.id),
            "queue": str(self.queue.id),
            "status": "ACTIVE",
            "medication_name": "Test Medication",
            "dosage": [
                {
                    "route": "oral",
                    "dose_quantity": 500,
                    "dose_unit": "mg",
                    "period": "8",
                    "period_unit": "hours",
                    "frequency": 3,
                    "duration": "7",
                    "duration_unit": "days",
                    "start_date": str(start_date),
                    "end_date": str(start_date + timedelta(days=1)),
                    "condition": "Take with food",
                    "patient_instruction": "Take after meals",
                }
            ],
        }

        url = reverse("prescriptions-list")
        response = self.client.post(url, data, **self.headers)
        assert response.status_code == 201
        self.assertEqual(Prescription.objects.count(), 1)

    def test_create_prescription_with_invalid_dates(self):
        """Test creating a prescription with invalid dosage dates."""
        today = datetime.now().date()
        data = {
            "patient": str(self.patient.id),
            "queue": str(self.queue.id),
            "status": "ACTIVE",
            "medication_name": "Test Medication",
            "dosage": [
                {
                    "route": "oral",
                    "dose_quantity": 500,
                    "dose_unit": "mg",
                    "period": "8",
                    "period_unit": "hours",
                    "frequency": 3,
                    "duration": "7",
                    "duration_unit": "days",
                    "start_date": str(today + timezone.timedelta(days=7)),
                    "end_date": str(today),  # Invalid: end date before start date,
                    "condition": "Take with food",
                    "patient_instruction": "Take after meals",
                }
            ],
        }

        url = reverse("prescriptions-list")
        response = self.client.post(url, data, **self.headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Dosage end date must be greater than the start date." in str(
            response.data
        )

    def test_create_prescription_with_past_end_date(self):
        """Test creating a prescription with a past end date."""
        today = timezone.now().date()
        data = {
            "patient": str(self.patient.id),
            "queue": str(self.queue.id),
            "status": "ACTIVE",
            "medication_name": "Test Medication",
            "dosage": [
                {
                    "route": "oral",
                    "dose_quantity": 500,
                    "dose_unit": "mg",
                    "period": "8",
                    "period_unit": "hours",
                    "frequency": 3,
                    "duration": "7",
                    "duration_unit": "days",
                    "start_date": str(today + timezone.timedelta(days=7)),
                    "end_date": str(today - timezone.timedelta(days=7)),
                    "condition": "Take with food",
                    "patient_instruction": "Take after meals",
                }
            ],
        }

        url = reverse("prescriptions-list")
        response = self.client.post(url, data, **self.headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Dosage end date cannot be in the past" in str(response.data)

    def test_create_prescription_with_missing_duration_unit(self):
        """Test creating a prescription with missing duration unit."""
        data = {
            "patient": str(self.patient.id),
            "queue": str(self.queue.id),
            "status": "ACTIVE",
            "medication_name": "Test Medication",
            "dosage": [
                {
                    "route": "oral",
                    "dose_quantity": 500,
                    "dose_unit": "mg",
                    "period": "8",
                    "period_unit": "hours",
                    "frequency": 3,
                    "duration": "7",
                    # Missing duration_unit
                    "start_date": "2024-11-11",
                    "end_date": "2024-11-18",
                    "condition": "Take with food",
                    "patient_instruction": "Take after meals",
                }
            ],
        }

        url = reverse("prescriptions-list")
        response = self.client.post(url, data, **self.headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Duration unit is required if duration is provided." in str(
            response.data
        )

    def test_create_prescription_with_negative_duration(self):
        """Test creating a prescription with negative duration."""
        data = {
            "patient": str(self.patient.id),
            "queue": str(self.queue.id),
            "status": "ACTIVE",
            "medication_name": "Test Medication",
            "dosage": [
                {
                    "route": "oral",
                    "dose_quantity": 500,
                    "dose_unit": "mg",
                    "period": "8",
                    "period_unit": "hours",
                    "frequency": 3,
                    "duration": "-7",
                    "duration_unit": "days",
                    "start_date": "2024-11-11",
                    "end_date": "2024-11-18",
                    "condition": "Take with food",
                    "patient_instruction": "Take after meals",
                }
            ],
        }

        url = reverse("prescriptions-list")
        response = self.client.post(url, data, **self.headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Duration must be a non-negative value." in str(response.data)

    def test_create_prescription_with_missing_period_unit(self):
        """Test creating a prescription with missing period unit."""
        data = {
            "patient": str(self.patient.id),
            "queue": str(self.queue.id),
            "status": "ACTIVE",
            "medication_name": "Test Medication",
            "dosage": [
                {
                    "route": "oral",
                    "dose_quantity": 500,
                    "dose_unit": "mg",
                    "period": "8",
                    "frequency": 3,
                    "duration": "7",
                    "duration_unit": "days",
                    "start_date": "2024-11-11",
                    "end_date": "2024-11-18",
                    "condition": "Take with food",
                    "patient_instruction": "Take after meals",
                }
            ],
        }

        url = reverse("prescriptions-list")
        response = self.client.post(url, data, **self.headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Period unit is required if period is provided." in str(response.data)

    def test_create_prescription_with_negative_period(self):
        """Test creating a prescription with negative period."""
        data = {
            "patient": str(self.patient.id),
            "queue": str(self.queue.id),
            "status": "ACTIVE",
            "medication_name": "Test Medication",
            "dosage": [
                {
                    "route": "oral",
                    "dose_quantity": 500,
                    "dose_unit": "mg",
                    "period": "-8",
                    "period_unit": "hours",
                    "frequency": 3,
                    "duration": "7",
                    "duration_unit": "days",
                    "start_date": "2024-11-11",
                    "end_date": "2024-11-18",
                    "condition": "Take with food",
                    "patient_instruction": "Take after meals",
                }
            ],
        }

        url = reverse("prescriptions-list")
        response = self.client.post(url, data, **self.headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Period must be a non-negative value." in str(response.data)

    def test_create_prescription_with_none_start_date(self):
        """Test creating a prescription with a None start date."""
        data = {
            "patient": str(self.patient.id),
            "queue": str(self.queue.id),
            "status": "ACTIVE",
            "medication_name": "Test Medication",
            "dosage": [
                {
                    "route": "oral",
                    "dose_quantity": 500,
                    "dose_unit": "mg",
                    "period": "8",
                    "period_unit": "hours",
                    "frequency": 3,
                    "duration": "7",
                    "duration_unit": "days",
                    "start_date": None,
                    "end_date": datetime.now().date() + timedelta(days=1),
                    "condition": "Take with food",
                    "patient_instruction": "Take after meals",
                }
            ],
        }

        url = reverse("prescriptions-list")
        response = self.client.post(url, data, **self.headers)
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_prescription_with_none_end_date(self):
        """Test creating a prescription with a None end date."""
        data = {
            "patient": str(self.patient.id),
            "queue": str(self.queue.id),
            "status": "ACTIVE",
            "medication_name": "Test Medication",
            "dosage": [
                {
                    "route": "oral",
                    "dose_quantity": 500,
                    "dose_unit": "mg",
                    "period": "8",
                    "period_unit": "hours",
                    "frequency": 3,
                    "duration": "7",
                    "duration_unit": "days",
                    "start_date": "2024-11-11",
                    "end_date": None,
                    "condition": "Take with food",
                    "patient_instruction": "Take after meals",
                }
            ],
        }

        url = reverse("prescriptions-list")
        response = self.client.post(url, data, **self.headers)
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_prescription_without_dosage(self):
        """Test creating a prescription without a dosage."""
        data = {
            "patient": str(self.patient.id),
            "queue": str(self.queue.id),
            "status": "ACTIVE",
            "medication_name": "Test Medication",
            "dosage": [],
        }

        url = reverse("prescriptions-list")
        response = self.client.post(url, data, **self.headers)
        assert response.status_code == status.HTTP_201_CREATED
