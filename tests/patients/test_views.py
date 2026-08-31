"""Test for the patients views."""
import os
import uuid
from itertools import cycle
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from model_bakery import baker, recipe
from sil_edge_connection.exceptions import RequestFailure

from sil_advantage.common.models import (
    Person,
    PersonContact,
    PersonID,
    RelatedPerson,
)
from sil_advantage.common.models.common_models import Attachment
from sil_advantage.common.models.organisation_models import Organisation
from sil_advantage.notifications.sms.models import SenderID
from sil_advantage.patients.models import (
    Patient,
    PatientCover,
    PatientListUpload,
)
from sil_advantage.patients.serializers import (
    PatientCoverSerializer,
    PatientSerializer,
)
from sil_advantage.settings.models import OrganisationSetting
from sil_advantage.sil_auth.models import SILUser
from tests.common.test_common_views import LoggedInMixin

MOCK_ROOT = "sil_advantage.patients.views."


class PatientDocumentViewTest(LoggedInMixin):
    """Test for the PatientDocumentViewSet view."""

    def setup(self):
        """Test set up for the view."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.maxDiff = None
        self.url_list = reverse("patientdocument-list")
        super().setUp()

    def extra_headers(self):
        """Workstation headers."""
        return {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    def _get_file(self, filename):
        """Get a test asset file."""
        filename = f"tests/assets/{filename}"
        with open(filename, "rb") as myfile:
            read_file = myfile.read()
            memory = SimpleUploadedFile(
                "image",
                read_file,
                content_type="image/jpeg",
            )
            return memory

    def test_create_patient_document(self):
        """Test patient creation with optional number."""
        create_document = reverse("patientdocument-list")
        headers = {
            "Content-Type": "application/json",
        }
        file = self._get_file("test_image.jpeg")
        org = self.global_organisation
        patient = baker.make(Patient, organisation=org)
        data = {
            "patient": patient.id,
            "content_type": "image/jpeg",
            "data": file,
            "title": "test-image-1",
            "size": "2000",
            "visit_date": "2023-04-03",
            "document_type": "CLINICAL_NOTES",
        }
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")

        response = self.client.post(
            create_document, data, format="multipart", **headers
        )
        assert response.status_code == 201, response.data
        assert response.data["document_type"] == "CLINICAL_NOTES"


@pytest.mark.usefixtures("default_transactional_sender")
class PatientViewTest(LoggedInMixin):
    """Test for PatientViewSet view."""

    def setUp(self):
        """Test setup for this view."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.maxDiff = None
        self.url_list = reverse("patient-list")
        self.workstation_data = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }
        self.default_transactional_sender = SenderID.objects.filter(
            name="BeWellApp"
        ).latest("created")
        super().setUp()

    def extra_headers(self):
        """Workstation headers."""
        return {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    def _get_file(self, filename):
        """Get a test asset file."""
        filename = f"tests/assets/{filename}"
        with open(filename, "rb") as myfile:
            read_file = myfile.read()
            memory = SimpleUploadedFile(
                filename,
                read_file,
                content_type="multipart/form-data",
            )
            return memory

    def test_create_patient(self):
        """Test patient creation with optional number."""
        create_patient = reverse("patient-list")
        headers = {
            "X-Cluster": uuid.uuid4(),
            "X-Branch": uuid.uuid4(),
            "X-Department": uuid.uuid4(),
            "X-Workstation": uuid.uuid4(),
        }
        data = {
            "person": {
                "first_name": "John",
                "last_name": "Doe",
                "marital_status": "single",
                "person_contacts": [
                    {
                        "contact": "+254721585473",
                        "contact_type": "phone_number",
                        "is_primary_contact": True,
                    },
                    {
                        "contact": "+254712345678",
                        "contact_type": "phone_number",
                        "is_primary_contact": False,
                    },
                    {
                        "contact": "fake@gmail.com",
                        "contact_type": "email",
                        "is_primary_contact": False,
                    },
                ],
                "person_ids": [],
                "person_photos": [],
            },
            "expected_delivery_date": "2024-11-11",
        }
        response = self.client.post(create_patient, data, **headers)
        assert response.status_code == 201, response.data
        assert response.data["person"]["first_name"] == "John"

        patient = Patient.objects.latest("created")
        patient_data = PatientSerializer(patient).data
        person_data = patient_data["person"]
        assert person_data["phone_number"] == "+254712345678"
        actual_phone_numbers = (
            contact["contact"]
            for contact in person_data["person_contacts"]
            if contact["contact_type"] == "phone_number"
        )
        self.assertCountEqual(actual_phone_numbers, ["+254712345678", "+254721585473"])
        assert patient.cluster_id == headers["X-Cluster"]
        assert patient.branch_id == headers["X-Branch"]
        assert patient.department_id == headers["X-Department"]
        assert patient.workstation_id == headers["X-Workstation"]
        assert str(patient.expected_delivery_date) == "2024-11-11"

    def test_create_patient_without_optional_number(self):
        """Test patient creation without optional number."""
        create_patient = reverse("patient-list")
        data = {
            "person": {
                "first_name": "John",
                "last_name": "Doe",
                "marital_status": "single",
                "person_contacts": [
                    {
                        "contact": "+254721585473",
                        "contact_type": "phone_number",
                        "is_primary_contact": True,
                    },
                    {
                        "contact": "fake@gmail.com",
                        "contact_type": "email",
                        "is_primary_contact": False,
                    },
                ],
                "person_ids": [],
                "person_photos": [],
            },
            **self.workstation_data,
        }
        response = self.client.post(create_patient, data)
        assert response.status_code == 201, response.data
        assert response.data["person"]["first_name"] == "John"

        patient = Patient.objects.latest("created")
        patient_data = PatientSerializer(patient).data
        person_data = patient_data["person"]
        assert person_data["phone_number"] == "+254721585473"
        actual_phone_numbers = (
            contact["contact"]
            for contact in person_data["person_contacts"]
            if contact["contact_type"] == "phone_number"
        )
        self.assertCountEqual(actual_phone_numbers, ["+254721585473"])
        self.assertEqual(person_data["person_ids"], [])

    def test_create_patient_with_id_details(self):
        """Test patient creation with optional number."""
        create_patient = reverse("patient-list")
        data = {
            "person": {
                "first_name": "John",
                "last_name": "Doe",
                "marital_status": "single",
                "person_contacts": [
                    {
                        "contact": "+254721585473",
                        "contact_type": "phone_number",
                        "is_primary_contact": True,
                    },
                    {
                        "contact": "+254712345678",
                        "contact_type": "phone_number",
                        "is_primary_contact": False,
                    },
                    {
                        "contact": "fake@gmail.com",
                        "contact_type": "email",
                        "is_primary_contact": False,
                    },
                ],
                "person_ids": [
                    {
                        "id_value": "15011998",
                        "id_document_type": "nationalID",
                    }
                ],
                "person_photos": [],
            },
            **self.workstation_data,
        }
        response = self.client.post(create_patient, data)
        assert response.status_code == 201, response.data
        assert response.data["person"]["first_name"] == "John"

        patient = Patient.objects.latest("created")
        patient_data = PatientSerializer(patient).data
        person_data = patient_data["person"]
        person_ids = person_data["person_ids"]
        assert len(person_ids) == 1
        person_id = person_ids[0]
        assert person_id["id_document_type"] == "nationalID"
        assert person_id["id_value"] == "15011998"

    def test_update_patient_details(self):
        """Test updating patient details."""
        create_patient = reverse("patient-list")
        data = {
            "person": {
                "first_name": "John",
                "last_name": "Doe",
                "marital_status": "single",
                "person_contacts": [
                    {
                        "contact": "+254721585473",
                        "contact_type": "phone_number",
                        "is_primary_contact": True,
                    },
                    {
                        "contact": "+254712345678",
                        "contact_type": "phone_number",
                        "is_primary_contact": False,
                    },
                    {
                        "contact": "fake@gmail.com",
                        "contact_type": "email",
                        "is_primary_contact": False,
                    },
                ],
                "person_ids": [
                    {
                        "id_value": "15011998",
                        "id_document_type": "nationalID",
                    }
                ],
                "person_photos": [],
            },
            **self.workstation_data,
        }
        response = self.client.post(create_patient, data)
        assert response.status_code == 201, response.data
        assert response.data["person"]["first_name"] == "John"
        patient = Patient.objects.latest("created")

        # update the person
        data = {
            "person": {
                "first_name": "Jane",
                "last_name": "Doe",
                "marital_status": "single",
                "person_contacts": [
                    {
                        "contact": "+254721585473",
                        "contact_type": "phone_number",
                        "is_primary_contact": True,
                    },
                    {
                        "contact": "+254712345678",
                        "contact_type": "phone_number",
                        "is_primary_contact": False,
                    },
                    {
                        "contact": "fake@gmail.com",
                        "contact_type": "email",
                        "is_primary_contact": False,
                    },
                ],
                "person_ids": [
                    {
                        "id_value": "8989",
                        "id_document_type": "nationalID",
                    }
                ],
                "person_photos": [],
            },
        }
        url = reverse("patient-detail", kwargs={"pk": patient.pk})
        response = self.client.patch(url, data)
        assert response.status_code == 200, response.data
        assert response.data["person"]["first_name"] == "Jane"

        patient.refresh_from_db()
        patient_data = PatientSerializer(patient).data
        person_data = patient_data["person"]
        person_ids = person_data["person_ids"]
        assert len(person_ids) == 1
        person_id = person_ids[0]
        assert person_id["id_document_type"] == "nationalID"
        assert person_id["id_value"] == "8989"

    def test_delete_patient(self):
        """Test patient delete method. Returns a status code of 204."""
        org = self.global_organisation
        person = baker.make(
            Person,
            organisation=org,
            **self.workstation_data,
        )
        patient = baker.make(
            Patient,
            person=person,
            organisation=org,
            **self.workstation_data,
        )
        url = reverse(
            "patient-detail",
            kwargs={"pk": patient.pk},
        )
        response = self.client.delete(url, **self.extra_headers())
        assert response.status_code == 204

    def test_patient_search(self):
        """Test searching for patients using various parameters."""
        org = self.global_organisation
        person_recipe = recipe.Recipe(
            Person,
            first_name=cycle(
                (
                    "Jane",
                    "John",
                    "Barack",
                )
            ),
            other_names="",
            last_name=cycle(
                (
                    "Doe",
                    "Doe",
                    "Obama",
                )
            ),
            organisation=org,
            **self.workstation_data,
        )
        jane_doe, john_doe, barack = person_recipe.make(_quantity=3)
        recipe.Recipe(
            PersonContact,
            contact=cycle(
                (
                    "+254712345678",
                    "+254799999999",
                    "obama@example.com",
                ),
            ),
            contact_type=cycle(
                (
                    "phone_number",
                    "phone_number",
                    "email",
                ),
            ),
            person=cycle(
                (
                    jane_doe,
                    john_doe,
                    barack,
                )
            ),
            **self.workstation_data,
        ).make(_quantity=3)
        recipe.Recipe(
            PersonID,
            id_value=cycle(("A123D", "23")),
            person=cycle(
                (
                    jane_doe,
                    barack,
                )
            ),
        ).make(_quantity=2)
        patient_recipe = recipe.Recipe(
            Patient,
            person=cycle(
                (
                    jane_doe,
                    john_doe,
                    barack,
                )
            ),
            **self.workstation_data,
        )
        patient_recipe.make(_quantity=3)

        url = reverse("patient-list")

        # no search param
        data = self.client.get(url).json()
        assert data["count"] == 3

        # search with first name "Barack"
        data = self.client.get(url + "?search=Barack").json()
        assert data["count"] == 1
        person = data["results"][0]["person"]
        assert person["person_display"] == "Barack Obama"

        # search with unknown name
        data = self.client.get(url + "?search=Steve").json()
        assert data["count"] == 0

        # search with phone number
        data = self.client.get(url + "?search=+254799999999").json()
        assert data["count"] == 1
        person = data["results"][0]["person"]
        assert person["person_display"] == "John Doe"

        # search with email
        data = self.client.get(url + "?search=obama@example.com").json()
        assert data["count"] == 1
        person = data["results"][0]["person"]
        assert person["person_display"] == "Barack Obama"

        # search with ID
        data = self.client.get(url + "?search=A123D").json()
        assert data["count"] == 1
        person = data["results"][0]["person"]
        assert person["person_display"] == "Jane Doe"

        data = self.client.get(url + "?search=23").json()
        assert data["count"] == 2

    def test_patient_ordering(self):
        """Test OrderingFilter."""
        org = self.global_organisation
        person_recipe = recipe.Recipe(
            Person,
            first_name=cycle(
                (
                    "Jane",
                    "John",
                    "Barack",
                )
            ),
            other_names="",
            last_name=cycle(
                (
                    "Doe",
                    "Doe",
                    "Obama",
                )
            ),
            organisation=org,
            **self.workstation_data,
        )
        jane_doe, john_doe, barack = person_recipe.make(_quantity=3)
        patient_recipe = recipe.Recipe(
            Patient,
            person=cycle(
                (
                    jane_doe,
                    john_doe,
                    barack,
                )
            ),
            **self.workstation_data,
        )
        patient_recipe.make(_quantity=3)

        url = reverse("patient-list")

        # test with no ordering
        data = self.client.get(url).json()
        assert [p["person"]["person_display"] for p in data["results"]] == [
            "Barack Obama",
            "John Doe",
            "Jane Doe",
        ]

        # test with ordering
        data = self.client.get(url + "?ordering=person__first_name").json()
        assert [p["person"]["person_display"] for p in data["results"]] == [
            "Barack Obama",
            "Jane Doe",
            "John Doe",
        ]

        # test with reverse ordering
        data = self.client.get(url + "?ordering=-person__first_name").json()
        assert [p["person"]["person_display"] for p in data["results"]] == [
            "John Doe",
            "Jane Doe",
            "Barack Obama",
        ]

    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_set_patient_health_id(self, mock_send_sms):
        """Test successfully set patient health id."""
        org = self.global_organisation
        person = baker.make(
            Person,
            organisation=org,
            **self.workstation_data,
        )
        patient = baker.make(
            Patient,
            person=person,
            organisation=org,
            **self.workstation_data,
        )
        baker.make(
            PersonContact,
            person=patient.person,
            contact_type="phone_number",
            contact="+254712345678",
        )

        url = reverse(
            "patient-set-health-id",
        )

        data = {"profile_id": patient.id, "health_id": "5113010000000028"}

        response = self.client.put(url, data, **self.extra_headers())

        assert response.status_code == 200
        patient.refresh_from_db()
        assert patient.global_health_id == "5113010000000028"

    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_set_patient_health_id_org_sms_true(self, mock_send_sms):
        """Test successfully set patient health id."""
        org = self.global_organisation
        person = baker.make(
            Person,
            organisation=org,
            **self.workstation_data,
        )
        patient = baker.make(
            Patient,
            person=person,
            organisation=org,
            **self.workstation_data,
        )
        baker.make(
            PersonContact,
            person=patient.person,
            contact_type="phone_number",
            contact="+254712345678",
        )
        send_global_health_id_sms = OrganisationSetting.set_org_setting(
            organisation=org,
            setting_name="patients:patient_global_health_id",
            value=True,
        )
        send_global_health_id_sms.save()

        url = reverse(
            "patient-set-health-id",
        )

        data = {"profile_id": patient.id, "health_id": "5113010000000028"}

        response = self.client.put(url, data, **self.extra_headers())

        priority = settings.CELERY_TASK_LOW_PRIORITY
        mock_send_sms.assert_called_once_with(
            queue="advantage_tasks",
            priority=priority,
            args=(
                "PATIENT_GLOBAL_HEALTH_ID",
                (
                    f"Welcome to {org.organisation_name}! "
                    f"Your registration is complete. "
                    f"Your Health ID is 5113 0100 0000 0028. "
                    f"Stay healthy with regular screenings. Thank you!"
                ),
                ["+254712345678"],
                org.slade_code,
                patient.branch_id,
                None,
            ),
            kwargs={"sender_id": self.default_transactional_sender.id},
        )
        assert response.status_code == 200
        patient.refresh_from_db()
        assert patient.global_health_id == "5113010000000028"

        # test no phone number
        person2 = baker.make(
            Person,
            organisation=org,
            **self.workstation_data,
        )
        patient2 = baker.make(
            Patient,
            person=person2,
            organisation=org,
            **self.workstation_data,
        )
        data = {"profile_id": patient2.id, "health_id": "5113010000000021"}

        response = self.client.put(url, data, **self.extra_headers())
        assert response.status_code == 200
        patient2.refresh_from_db()
        assert patient2.global_health_id == "5113010000000021"

    def test_set_patient_health_id_invalid_patient_id(self):
        """Test successfully set patient health id."""
        url = reverse(
            "patient-set-health-id",
        )

        data = {"profile_id": uuid.uuid4(), "health_id": "5113010000000028"}

        response = self.client.put(url, data, **self.extra_headers())

        assert response.status_code == 400
        assert response.data["error"] == "invalid profile id"

    def test_linking_and_unlinking_next_of_kin(self):
        """Test linking & unlinking next of kin."""
        husb = baker.make(
            Patient,
            person__first_name="John",
            person__last_name="Doe",
            person__gender="MALE",
            organisation=self.global_organisation,
            **self.workstation_data,
        )
        patient_link_url = reverse(
            "patient-link-related",
            kwargs={"pk": husb.pk},
        )
        payload = {
            "first_name": "Jane",
            "last_name": "Doe",
            "gender": "FEMALE",
            "date_of_birth": "2000-01-01",
            "person_contacts": [
                {
                    "contact_type": "phone_number",
                    "contact": "+254790360360",
                }
            ],
            "person_ids": [],
            "relationship": "WIFE",
        }

        response = self.client.post(patient_link_url, data=payload)
        assert response.status_code == 200

        list_related_url = reverse(
            "patient-related-persons",
            kwargs={"pk": husb.pk},
        )
        response = self.client.get(list_related_url, **self.extra_headers()).json()
        assert len(response) == 1
        assert response[0]["relationship"] == "WIFE"
        assert response[0]["relationship_display"] == "Wife"
        assert response[0]["related"]["first_name"] == "Jane"

        reverse_relation = RelatedPerson.objects.get(related=husb.person)
        assert reverse_relation.relationship == "HUSB"
        assert Patient.objects.count() == 1

        # Search then Update
        payload = response[0]["related"]
        payload["first_name"] = "Marie"
        payload["relationship"] = "SPS"

        response = self.client.put(patient_link_url, data=payload)
        assert response.status_code == 200

        response = self.client.get(list_related_url, **self.extra_headers()).json()
        assert len(response) == 1
        assert response[0]["relationship"] == "SPS"
        assert response[0]["relationship_display"] == "Spouse"
        assert response[0]["related"]["first_name"] == "Marie"

        reverse_relation.refresh_from_db()
        assert reverse_relation.relationship == "SPS"
        assert Patient.objects.count() == 1

    @patch("sil_advantage.patients.tasks.process_patient_list_upload.apply_async")
    def test_process_file_upload(self, mock_process_patient_list_upload):
        """Test processing file uploads."""
        headers = {
            "X-Cluster": uuid.uuid4(),
            "X-Branch": uuid.uuid4(),
            "X-Department": uuid.uuid4(),
            "X-Workstation": uuid.uuid4(),
            "Content-Type": "multipart/form-data",
        }

        process_file_upload_url = reverse(
            "patient-process-file-upload",
        )
        field_mapping = {
            "first_name": "",
            "last_name": "",
            "full_name": "PATIENT NAME",
            "other_names": "",
            "age": "AGE",
            "gender": "GENDER",
            "date_of_birth": "",
            "phone_number": "PHONE NUMBER",
            "patient_number": "PATIENT NUMBER",
        }

        assets_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "assets")
        )
        data = File(open(assets_dir + "/Test Patient Records.xlsx", "rb"))
        file = SimpleUploadedFile(
            "Test Patient Records.xlsx",
            data.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        payload = {"file": file, **field_mapping}

        response = self.client.post(
            process_file_upload_url,
            data=payload,
            content_disposition="file; filename=Test Patient Records.xlsx",
            format="multipart",
            **headers,
        )
        attachment = Attachment.objects.all()
        assert attachment.count() == 1

        patient_list_upload = PatientListUpload.objects.all()
        assert patient_list_upload.count() == 1

        mock_process_patient_list_upload.assert_called_once_with(
            queue="advantage_tasks",
            priority=5,
            args=(patient_list_upload[0].id,),
        )
        assert response.status_code == 202

        data = response.data
        assert data["process_state"] == "IN_PROGRESS"

    def test_file_upload_fields(self):
        """Test providing patient file upload fields."""
        expected_fields = [
            "first_name",
            "last_name",
            "full_name",
            "other_names",
            "phone_number",
            "patient_number",
            "gender",
            "age",
            "date_of_birth",
        ]

        patient_file_upload_fields_url = reverse(
            "patient-file-upload-fields",
        )

        response = self.client.get(patient_file_upload_fields_url)
        assert response.status_code == 200
        assert response.data == expected_fields

    @patch("sil_advantage.common.api_clients.health_crm.HealthCRM")
    def test_search_for_person_successful_call(self, mock_get_health_crm_client):
        """Test successful persons proxy elastic search to Health CRM."""
        search_param = "Brown"
        url = f'{reverse("patient-person-search")}?search={search_param}'

        mock_client_instance = MagicMock()
        mock_get_health_crm_client.return_value = mock_client_instance
        mock_persons_list = MagicMock(
            return_value={
                "count": 2,
                "next": None,
                "previous": None,
                "page_size": 20,
                "current_page": 1,
                "total_pages": 1,
                "start_index": 1,
                "end_index": 2,
                "results": [
                    {
                        "id": "b7c04b80-2f9c-4df2-8bb0-cf2cba428a91",
                        "name": "Moses Brown Peter",
                        "age": 38,
                        "date_of_birth": "1985-10-25",
                        "gender": None,
                        "email": None,
                        "phone_number": "+25471111111",
                        "sil_global_identifier": "5111 0100 0000 6431",
                        "services": [
                            {
                                "id": "3b27d817-352e-4b36-8630-5218fbceca92",
                                "name": "SLADE_ADVANTAGE",
                                "label": "SLADE_ADVANTAGE",
                                "code": "01",
                                "callback_url": "https://api.advantage.com/",
                                "description": "It is a software solution.",
                            }
                        ],
                        "created": "2023-08-14T17:36:29.445758+03:00",
                        "updated": "2023-08-14T17:36:29.445784+03:00",
                    },
                    {
                        "id": "ac1147db-ffb2-4eea-855b-54caa906fde8",
                        "name": "Ann Brown Wamaitha",
                        "age": 24,
                        "date_of_birth": "1999-07-30",
                        "gender": None,
                        "email": None,
                        "phone_number": "+25400000000",
                        "sil_global_identifier": "5111 0100 0000 4758",
                        "services": [
                            {
                                "id": "3b27d817-352e-4b36-8630-5218fbceca92",
                                "name": "SLADE_ADVANTAGE",
                                "label": "SLADE_ADVANTAGE",
                                "code": "01",
                                "callback_url": "https://api.advantage.com/",
                                "description": "It is a software solution.",
                            }
                        ],
                        "created": "2023-08-14T17:36:24.326676+03:00",
                        "updated": "2023-08-14T17:36:24.326701+03:00",
                    },
                ],
            }
        )
        mock_client_instance.persons.search = mock_persons_list

        response = self.client.get(url)

        mock_persons_list.assert_called_once_with(
            params={
                "search": [search_param],
            }
        )

        assert response.status_code == 200
        assert response.data
        data = response.data
        assert data["count"] == 2
        assert data["results"][0]["name"] == "Moses Brown Peter"
        assert data["results"][0]["age"] == 38
        assert data["results"][0]["date_of_birth"] == "1985-10-25"
        assert data["results"][0]["sil_global_identifier"] == "5111 0100 0000 6431"
        assert data["results"][1]["name"] == "Ann Brown Wamaitha"
        assert data["results"][1]["age"] == 24
        assert data["results"][1]["date_of_birth"] == "1999-07-30"
        assert data["results"][1]["sil_global_identifier"] == "5111 0100 0000 4758"

    @patch("sil_advantage.common.api_clients.health_crm.HealthCRM")
    def test_search_for_business_partner_unsuccessful_call(
        self, mock_health_crm_client
    ):
        """Test failure for search for a business partner."""
        mock_cm = MagicMock()
        mock_cm.persons.search.side_effect = RequestFailure(
            "invalid",
            {
                "status_code": 400,
                "response": "Bad Request",
                "method": "GET",
                "url": "/maybe",
                "request": "req",
                "payload": '{ "error": "Unauthenticated request" }',
            },
        )

        mock_health_crm_client.return_value = mock_cm
        url = f'{reverse("patient-person-search")}?search=Brown'
        response = self.client.get(url)

        assert response.status_code == 400
        assert response.data == "Bad Request"

    def test_patient_list_upload_download_urls(self):
        """Test returning patient list upload download urls."""
        assets_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "assets")
        )
        data = File(open(assets_dir + "/Test Patient Records.xlsx", "rb"))
        file = SimpleUploadedFile(
            "Test Patient Records.xlsx",
            data.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        attachment = baker.make(
            Attachment,
            content_type=file.content_type,
            data=file,
            title=file.name,
            size=file.size,
            created_by=self.user.guid,
            updated_by=self.user.guid,
            **self.workstation_data,
        )

        failed_upload_file_attachment = baker.make(
            Attachment,
            content_type=file.content_type,
            data=data,
            title=data.name,
            size=data.size,
            created_by=self.user.guid,
            updated_by=self.user.guid,
            **self.workstation_data,
        )

        baker.make(
            PatientListUpload,
            upload_file=attachment,
            failed_uploads_file=failed_upload_file_attachment,
            process_state="IN_PROGRESS",
            upload_type="GENERAL",
            created_by=self.user.guid,
            updated_by=self.user.guid,
            **self.workstation_data,
        )

        url = reverse(
            "patientlistupload-list",
        )
        response = self.client.get(url, **self.extra_headers()).json()

        assert response["results"][0]["upload_file_url"] is not None
        assert response["results"][0]["failed_upload_file_url"] is not None
        assert response["results"][0]["file_name"] == "Test Patient Records.xlsx"

    def test_filter_patients_with_branch_id(self):
        """Test filtering patient per branch."""
        # Create a patient for a specific branch
        url = reverse("patient-list")
        self.workstation_data_2 = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50888c",
            "branch_id": "9f273420-b325-475c-a1a5-83451aeb837f",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe4",
        }
        person1 = baker.make(
            Person,
            organisation=self.global_organisation,
            **self.workstation_data,
        )
        person2 = baker.make(
            Person,
            organisation=self.global_organisation,
            **self.workstation_data_2,
        )
        baker.make(
            Patient,
            person=person1,
            organisation=self.global_organisation,
            **self.workstation_data,
        )
        baker.make(
            Patient,
            person=person2,
            organisation=self.global_organisation,
            **self.workstation_data_2,
        )
        response = self.client.get(url, **self.extra_headers())

        # Check response and patient count
        assert response.status_code == 200
        self.assertEqual(response.data["count"], 1)


class PatientCoverViewTest(LoggedInMixin):
    """Test for PatientCoverViewSet view."""

    def setUp(self):
        """Test setup for this view."""
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        org = self.global_organisation
        person = baker.make(
            Person, first_name="Sarah", last_name="Doe", organisation=org
        )
        self.patient = baker.make(Patient, person=person, organisation=org)
        self.workstation_data = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }
        super().setUp()

    def extra_headers(self):
        """Workstation headers."""
        return {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    def test_create_patientcover(self):
        """Test patient cover creation."""
        org = baker.make(Organisation)
        user = uuid.uuid4()

        create_cover = reverse("patientcover-list")
        headers = {
            "X-Cluster": uuid.uuid4(),
            "X-Branch": uuid.uuid4(),
            "X-Department": uuid.uuid4(),
            "X-Workstation": uuid.uuid4(),
        }

        data = {
            "scheme_name": "NHIP",
            "member_number": "NH132",
            "patient": self.patient.id,
            "scheme_id": "eaca7a4c-8d0f-4906-bccf-eacf492cfd1c",
            "payer_id": "eaca7a4c-8d0f-4906-bccf-eacf492cfd1d",
            "valid_from": "2024-03-15",
            "valid_to": "2024-03-16",
            "organisation": org.id,
            "created_by": user,
            "updated_by": user,
        }
        response = self.client.post(create_cover, data, **headers)
        assert response.status_code == 201, response.data
        assert response.data["scheme_name"] == "NHIP"

        cover = PatientCover.objects.latest("created")
        cover_data = PatientCoverSerializer(cover).data
        assert cover_data["patient_name"] == "Sarah Doe"
        assert cover.cluster_id == headers["X-Cluster"]
        assert cover.branch_id == headers["X-Branch"]
        assert cover.department_id == headers["X-Department"]
        assert cover.workstation_id == headers["X-Workstation"]

    def test_update_patient_cover_details(self):
        """Test updating patient cover details."""
        org = baker.make(Organisation)
        user = uuid.uuid4()
        create_cover = reverse("patientcover-list")
        headers = {
            "X-Cluster": uuid.uuid4(),
            "X-Branch": uuid.uuid4(),
            "X-Department": uuid.uuid4(),
            "X-Workstation": uuid.uuid4(),
        }

        data = {
            "scheme_name": "NHIF",
            "member_number": "NH132",
            "patient": self.patient.id,
            "scheme_id": "eaca7a4c-8d0f-4906-bccf-eacf492cfd1c",
            "payer_id": "eaca7a4c-8d0f-4906-bccf-eacf492cfd1d",
            "valid_from": "2024-03-15",
            "valid_to": "2024-03-16",
            "organisation": org.id,
            "created_by": user,
            "updated_by": user,
        }
        response = self.client.post(create_cover, data, **headers)
        assert response.status_code == 201, response.data
        assert response.data["scheme_name"] == "NHIF"
        assert response.data["member_number"] == "NH132"

        cover = PatientCover.objects.latest("created")

        data = {
            "scheme_name": "Savannah",
            "member_number": "SIL132",
            "patient": self.patient.id,
            "scheme_id": "eaca7a4c-8d0f-4906-bccf-eacf492cfd1c",
            "payer_id": "eaca7a4c-8d0f-4906-bccf-eacf492cfd1d",
            "valid_from": "2024-03-15",
            "valid_to": "2024-03-16",
            "organisation": org.id,
            "created_by": user,
            "updated_by": user,
        }
        url = reverse("patientcover-detail", kwargs={"pk": cover.pk})
        response = self.client.patch(url, data, **headers)
        assert response.status_code == 200, response.data
        assert response.data["scheme_name"] == "Savannah"
        assert response.data["member_number"] == "SIL132"
        cover.refresh_from_db()
        cover_data = PatientCoverSerializer(cover).data
        assert cover_data["patient_name"] == "Sarah Doe"
        assert cover_data["scheme_name"] == "Savannah"

    def test_delete_patientcover(self):
        """Test patient cover delete."""
        user = uuid.uuid4()
        cover = baker.make(
            PatientCover,
            scheme_name="NHIS",
            member_number="NH132",
            patient=self.patient,
            scheme_id="eaca7a4c-8d0f-4906-bccf-eacf492cfd1c",
            payer_id="eaca7a4c-8d0f-4906-bccf-eacf492cfd1d",
            valid_from="2024-03-15",
            valid_to="2024-03-16",
            organisation=self.global_organisation,
            created_by=user,
            updated_by=user,
            **self.workstation_data,
        )
        url = reverse("patientcover-detail", kwargs={"pk": cover.pk})
        response = self.client.delete(url, **self.extra_headers())
        assert response.status_code == 204

    def test_patientcover_search(self):
        """Test searching for patient covers using various paramenters."""
        org = self.global_organisation
        person_recipe = recipe.Recipe(
            Person,
            first_name=cycle(
                (
                    "Jane",
                    "John",
                    "Barack",
                )
            ),
            other_names="",
            last_name=cycle(
                (
                    "Doe",
                    "Doe",
                    "Obama",
                )
            ),
            organisation=org,
            **self.workstation_data,
        )
        jane_doe, john_doe, barack = person_recipe.make(_quantity=3)
        patient_recipe = recipe.Recipe(
            Patient,
            person=cycle(
                (
                    jane_doe,
                    john_doe,
                    barack,
                )
            ),
            **self.workstation_data,
        )
        jane, john, obama = patient_recipe.make(_quantity=3)
        user = uuid.uuid4()  # Assuming user is defined
        scheme_id = "eaca7a4c-8d0f-4906-bccf-eacf492cfd1c"
        payer_id = "eaca7a4c-8d0f-4906-bccf-eacf492cfd1d"
        valid_from = "2024-03-15"
        valid_to = "2024-03-16"
        cover_recipe = recipe.Recipe(
            PatientCover,
            scheme_name="NHIS",
            member_number="NH132",
            patient=cycle(
                (
                    jane,
                    john,
                    obama,
                )
            ),
            scheme_id=scheme_id,
            payer_id=payer_id,
            valid_from=valid_from,
            valid_to=valid_to,
            organisation=self.global_organisation,
            created_by=user,
            updated_by=user,
            **self.workstation_data,
        )
        cover_recipe.make(_quantity=3)
        url = reverse("patientcover-list")

        # no search param
        data = self.client.get(url).json()
        assert data["count"] == 3

        # search by first name
        data = self.client.get(url + "?search=Barack").json()
        assert data["count"] == 1

        # search by last name
        data = self.client.get(url + "?search=obama").json()
        assert data["count"] == 1

        # search by scheme name
        data = self.client.get(url + "?search=nhis").json()
        assert data["count"] == 3

        # search by member number
        data = self.client.get(url + "?search=nh132").json()
        assert data["count"] == 3

        # search with unknown name
        data = self.client.get(url + "?search=Sarah").json()
        assert data["count"] == 0


class PatientListUploadViewTest(LoggedInMixin):
    """Tests for Patient list uploads."""

    def setUp(self):
        """Test setup for this view."""
        self.org = self.global_organisation
        self.workstation_data = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }
        super().setUp()

    def extra_headers(self):
        """Workstation headers."""
        return {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    def test_listing_patient_file_uploads(self):
        """Test listing of patient list uploads."""
        assets_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "assets")
        )
        data = File(open(assets_dir + "/Test Patient Records.xlsx", "rb"))
        file = SimpleUploadedFile(
            "Test Patient Records.xlsx",
            data.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        file_upload_obj = baker.make(
            Attachment,
            data=file,
            title=file.name,
            size=file.size,
            content_type=file.content_type,
            organisation=self.org,
            **self.workstation_data,
        )

        baker.make(
            PatientListUpload,
            upload_file=file_upload_obj,
            organisation=self.org,
            **self.workstation_data,
        )
        list_patient_file_uploads = reverse("patientlistupload-list")

        response = self.client.get(list_patient_file_uploads, **self.extra_headers())
        assert response.status_code == 200
        assert response.data["count"] == 1
