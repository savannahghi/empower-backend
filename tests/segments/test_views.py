"""Segment view tests."""
import os
import uuid
from datetime import timedelta
from decimal import Decimal
from itertools import cycle
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone, translation
from model_bakery import baker, recipe
from rest_framework import status

from sil_advantage.common.models import Person, PersonContact
from sil_advantage.common.models.common_models import (
    Attachment,
    Consent,
    ConsentType,
)
from sil_advantage.common.utilities.cube import CubeJS
from sil_advantage.notifications.sms.models import SMS, SenderID
from sil_advantage.patients.models import Patient, PatientListUpload
from sil_advantage.segments.models import (
    Filter,
    FilterAllowedOperations,
    FilterChoiceSource,
    FilterGroup,
    FilterGroupFilter,
    FilterValueType,
    Journey,
    JourneyAttributes,
    MessageTemplate,
    MessageTemplateTransitionLog,
    Segment,
    SegmentMember,
    SegmentMemberStatus,
    SegmentMemberTransitionLog,
    SegmentMessage,
    SegmentMessageDelivery,
    SegmentMessageDeliveryType,
    SegmentMessageStatus,
    SegmentStatus,
    SegmentTransitionLog,
    SegmentUpload,
)
from sil_advantage.segments.models.filters import FilterExecutionStatus
from sil_advantage.sil_auth.models import SILUser
from tests.common.test_common_views import LoggedInMixin

pytestmark = pytest.mark.django_db


class SegmentViewsetTestCase(LoggedInMixin):
    """Test Segment viewset."""

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

    def test_create_segment(self):
        """Test creating a segment."""
        payload = {
            "name": "Test Segment",
            "description": "This is a test segment",
            "status": "ACTIVE",
        }

        url = reverse("segment-list")
        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 201
        self.assertEqual(Segment.objects.count(), 1)
        assert response.data["name"] == "Test Segment"

    def test_create_ussd_segment(self):
        """Test creating a segment."""
        payload = {
            "name": "USSD Test Segment",
            "description": "This is a test ussd segment",
            "status": "ACTIVE",
            "ussd_enabled": True,
        }

        url = reverse("segment-list")
        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 201
        self.assertEqual(Segment.objects.count(), 1)
        assert response.data["name"] == "USSD Test Segment"
        assert response.data["ussd_enabled"] is True

    def test_list_segments(self):
        """Test listing segments."""
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )

        baker.make(
            SegmentMember,
            person=self.person,
            segment=segment,
            created_by=self.user.id,
            status=SegmentMemberStatus.CONFIRMED,
        )

        url = reverse("segment-list")

        response = self.client.get(url)
        result = response.json()

        assert result["count"] == 1
        assert result["results"][0]["member_count"] == 1

    @patch("sil_advantage.segments.tasks.send_segment_joining_messages.apply_async")
    def test_clinical_add_member_to_segment_with_consent(
        self, mock_send_segment_joining_messages
    ):
        """Test adding a member to a segment."""
        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            label="CERVICAL_CANCER_HIGH_RISK",
        )
        message = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
            created_by=self.user.id,
        )
        baker.make(
            SegmentMessage,
            template=message,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
            segment=segment,
            created_by=self.user.id,
            send_on_segment_join=True,
        )
        message_two = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
            created_by=self.user.id,
        )
        baker.make(
            SegmentMessage,
            template=message_two,
            segment=segment,
            created_by=self.user.id,
            delivery_type=SegmentMessageDeliveryType.SCHEDULED_RECURRENT,
            sequence_interval="0 13 * * WED",
            send_on_segment_join=True,
        )
        baker.make(
            PersonContact,
            person=self.person,
            contact_type="phone_number",
            contact="+254722060000",
        )

        url = reverse(
            "segment-clinical",
        )
        payload = {
            "clinical_id": str(self.patient.clinical_id),
            "segment_label": "CERVICAL_CANCER_HIGH_RISK",
        }

        response = self.client.post(url, payload)
        assert response.status_code == 200

        mock_send_segment_joining_messages.assert_called_once()

        segment = Segment.objects.all().latest("created")
        assert response.data["segment"]["id"] == str(segment.id)

    def test_clinical_add_member_to_segment_no_consent(self):
        """Test adding a member to a segment."""
        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            label="CERVICAL_CANCER_HIGH_RISK",
        )
        message = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
        )
        baker.make(
            SegmentMessage,
            template=message,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
            segment=segment,
            created_by=self.user.id,
        )

        assert SegmentMessageDelivery.objects.count() == 0

        url = reverse(
            "segment-clinical",
        )
        payload = {
            "clinical_id": str(self.patient.clinical_id),
            "segment_label": "CERVICAL_CANCER_HIGH_RISK",
        }

        response = self.client.post(url, payload)
        assert response.status_code == 200

        assert SegmentMessageDelivery.objects.count() == 0
        segment = Segment.objects.all().latest("created")
        assert response.data["segment"]["id"] == str(segment.id)

    def test_clinical_add_member_to_non_existing_segment(self):
        """Test adding member to a segment that does not exist."""
        url = reverse(
            "segment-clinical",
        )
        payload = {
            "clinical_id": str(self.patient.clinical_id),
            "segment_label": "CERVICAL_CANCER_HIGH_RISK",
        }
        response = self.client.post(url, payload)
        assert response.status_code == 200

        segment = Segment.objects.all()
        assert segment.count() == 1
        assert response.data["segment"]["id"] == str(segment[0].id)

    def test_clinical_add_member_without_clinical_id(self):
        """Test adding member to a segment without a clinical id."""
        url = reverse(
            "segment-clinical",
        )
        payload = {
            "clinical_id": "087c9c78-04d2-4df2-8b6d-ba06bbaf8fc2",
            "segment_label": "CERVICAL_CANCER_HIGH_RISK",
        }
        response = self.client.post(url, payload)
        assert response.status_code == 404

    def test_clinical_add_existing_member_to_segment(self):
        """Test adding a member to a segment."""
        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            label="CERVICAL_CANCER_HIGH_RISK",
        )
        message = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
        )
        baker.make(
            SegmentMessage,
            template=message,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
            segment=segment,
            created_by=self.user.id,
        )

        # the existing member
        baker.make(
            SegmentMember,
            organisation=self.global_organisation,
            created_by=self.user.id,
            segment=segment,
            person=self.person,
        )

        url = reverse(
            "segment-clinical",
        )
        payload = {
            "clinical_id": str(self.patient.clinical_id),
            "segment_label": "CERVICAL_CANCER_HIGH_RISK",
        }

        response = self.client.post(url, payload)
        assert response.status_code == 200

    @patch("sil_advantage.patients.tasks.process_patient_list_upload.apply_async")
    def test_segment_upload(self, mock_process_patient_list_upload):
        """Test uploading members to a segment."""
        baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            label="CERVICAL_CANCER_HIGH_RISK",
            **self.workstation_data,
        )
        segment = Segment.objects.all().latest("created")

        segment_upload_url = reverse(
            "segment-upload",
            kwargs={"pk": segment.id},
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
            segment_upload_url,
            data=payload,
            content_disposition="file; filename=Test Patient Records.xlsx",
            format="multipart",
            **self.headers,
        )

        attachment = Attachment.objects.all()
        assert attachment.count() == 1

        patient_list_upload = PatientListUpload.objects.all()
        assert patient_list_upload.count() == 1

        segment_upload = SegmentUpload.objects.all()
        assert segment_upload.count() == 1

        mock_process_patient_list_upload.assert_called_once_with(
            queue="advantage_tasks",
            priority=5,
            args=(patient_list_upload[0].id,),
            kwargs={"segment_upload_id": segment_upload[0].id},
        )

        data = response.data
        assert response.status_code == 202
        assert data["process_state"] == "IN_PROGRESS"
        assert data["upload_type"] == "SEGMENT"

        # test search fields
        url = reverse("segmentupload-list")

        response = self.client.get(
            url + "?search=Test Patient Records",
            **self.headers,
        ).json()
        assert response["count"] == 1

        response = self.client.get(
            url + "?search=Oregon Upload",
            **self.headers,
        ).json()
        assert response["count"] == 0

    def test_search_segment_by_name(self):
        """Test searching segments by name."""
        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            name="Demo Segment",
            **self.workstation_data,
        )

        baker.make(
            SegmentMember,
            person=self.person,
            segment=segment,
            created_by=self.user.id,
            **self.workstation_data,
        )

        url = reverse("segment-list")
        response = self.client.get(
            url + "?search=Demo Segment",
            **self.headers,
        )
        result = response.json()

        assert result["count"] == 1
        assert result["results"][0]["name"] == "Demo Segment"

        response_two = self.client.get(
            url + "?search=Nairobi Segment",
            **self.headers,
        )
        result_two = response_two.json()

        assert result_two["count"] == 0

    def test_list_segment_members(self):
        """Test listing segment members."""
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )

        person_one = baker.make(
            Person,
            first_name="Jane",
            last_name="Doe",
            organisation=self.global_organisation,
        )
        person_two = baker.make(
            Person,
            first_name="John",
            last_name="Doe",
            organisation=self.global_organisation,
        )
        person_three = baker.make(
            Person,
            first_name="John",
            last_name="Doe",
            organisation=self.global_organisation,
        )

        baker.make(
            SegmentMember,
            person=person_one,
            segment=segment,
            created_by=self.user.id,
            status="DRAFT",
        )
        baker.make(
            SegmentMember,
            person=person_two,
            segment=segment,
            created_by=self.user.id,
            status="CONFIRMED",
        )
        baker.make(
            SegmentMember,
            person=person_three,
            segment=segment,
            created_by=self.user.id,
            status="RETIRED",
        )

        url = reverse("segmentmember-list")

        response = self.client.get(
            f"{url}?segment={str(segment.id)}&segment_id={str(segment.id)}&status=DRAFT"
        )
        result = response.json()

        assert result["count"] == 1
        assert result["results"][0]["status"] == "DRAFT"

        response = self.client.get(
            f"{url}?segment={str(segment.id)}&segment_id={str(segment.id)}&status=CONFIRMED"
        )
        result = response.json()

        assert result["count"] == 1
        assert result["results"][0]["status"] == "CONFIRMED"

        response = self.client.get(
            f"{url}?segment={str(segment.id)}&segment_id={str(segment.id)}&status=RETIRED"
        )
        result = response.json()

        assert result["count"] == 1
        assert result["results"][0]["status"] == "RETIRED"

    def test_transition_segment(self):
        """Test transitioning a Segment's status."""
        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
            **self.workstation_data,
        )
        segment_two = baker.make(
            Segment,
            organisation=self.global_organisation,
            **self.workstation_data,
        )

        url = reverse(
            "segment-transition", kwargs={"id": segment.id, "status": "RETIRED"}
        )
        url_two = reverse(
            "segment-transition", kwargs={"id": segment_two.id, "status": "RETIRED"}
        )
        self.client.patch(url)
        self.client.patch(url_two)

        segment.refresh_from_db()
        assert segment.status == SegmentStatus.RETIRED

        logs = SegmentTransitionLog.objects.get(segment_id=segment.id)
        assert logs.segment.id == segment.id
        assert logs.status_to == SegmentStatus.RETIRED
        assert logs.status_from == SegmentStatus.ACTIVE

        url = reverse(
            "segment-transition", kwargs={"id": segment.id, "status": "ACTIVE"}
        )
        self.client.patch(url)
        url = reverse("segmenttransitionlog-list")

        response = self.client.get(url, **self.headers).json()
        assert response["count"] == 3

        response = self.client.get(
            url + f"?segment={segment.id}",
            **self.headers,
        ).json()
        assert response["count"] == 2
        assert response["results"][0]["updated_by_name"] == "John Doe"

    def test_create_segment_without_filters(self):
        """Test creating a segment without filter criteria."""
        payload = {
            "name": "Example Segment",
            "description": "Example Description",
        }
        url = reverse("segment-list")

        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 201

    @patch("sil_advantage.segments.tasks.execute_segment_filter_cube_query.apply_async")
    def test_create_segment_with_filters(self, mock_execute_segment_filter_query):
        """Test creating a segment with filter criteria."""
        filter_one = baker.make(
            Filter,
            name="Gender",
            allowed_operations=[FilterAllowedOperations.EQUALS],
            value_type=FilterValueType.CLOSE_ENDED,
            cube_config={
                "member": "patients_poc.gender",
            },
        )
        filter_two = baker.make(
            Filter,
            name="Age",
            allowed_operations=[
                FilterAllowedOperations.EQUALS,
                FilterAllowedOperations.GREATER_THAN,
            ],
            value_type=FilterValueType.CLOSE_ENDED,
            cube_config={
                "member": "patients_poc.age",
            },
        )

        payload = {
            "name": "Example Segment",
            "description": "Example Description",
            "filter_groups": [
                {
                    "name": "Group 1",
                    "filters": [
                        {
                            "filter_id": str(filter_one.id),
                            "operation": "EQUALS",
                            "value": "MALE",
                        },
                        {
                            "filter_id": str(filter_two.id),
                            "operation": "GREATER_THAN",
                            "value": "20",
                        },
                    ],
                },
                {
                    "name": "Group 2",
                    "filters": [
                        {
                            "filter_id": str(filter_two.id),
                            "operation": "GREATER_THAN",
                            "value": "45",
                        }
                    ],
                },
            ],
        }
        url = reverse("segment-list")

        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 201

        result = response.json()
        segment_id = result["id"]

        assert FilterGroup.objects.filter(segment=segment_id).count() == 2
        assert FilterGroupFilter.objects.count() == 3

        mock_execute_segment_filter_query.assert_called_once_with(
            queue="advantage_tasks",
            priority=10,
            args=(segment_id,),
        )


class MessageTemplateViewsetTestCase(LoggedInMixin):
    """Test message template viewset."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()

        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")

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

    def tearDown(self):
        """Tear down test."""
        translation.activate(settings.MODELTRANSLATION_DEFAULT_LANGUAGE)

    def test_list_templates(self):
        """Test listing templates."""
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )

        template_one = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
        )
        template_two = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            parent=template_one,
        )
        baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            parent=template_two,
        )

        baker.make(
            SegmentMessage,
            template=template_one,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
            segment=segment,
            created_by=self.user.id,
        )

        url = reverse("messagetemplate-list")

        response = self.client.get(url)
        result = response.json()

        # child/sequenced messages are not included
        assert result["count"] == 1

    def test_list_sequence_templates(self):
        """Test listing segments."""
        main_template = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            template="Message One",
        )

        template_two = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            parent=main_template,
            template="Message Two",
        )
        template_three = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            parent=template_two,
            template="Message Three",
        )

        url = reverse("messagetemplate-templates", kwargs={"pk": main_template.id})

        response = self.client.get(url)
        result = response.json()

        assert result["count"] == 3
        # The results should be ordered
        assert result["results"][1]["id"] == str(template_two.id)
        assert result["results"][2]["id"] == str(template_three.id)

        template_four = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            parent=template_three,
            template="Message Four",
        )

        template_five = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            parent=template_four,
            template="Message Five",
        )

        response_two = self.client.get(url)
        result_two = response_two.json()

        assert result_two["count"] == 5
        # The results should be ordered
        assert result_two["results"][1]["id"] == str(template_two.id)
        assert result_two["results"][1]["sequence"] == "2"

        assert result_two["results"][2]["id"] == str(template_three.id)
        assert result_two["results"][2]["sequence"] == "3"

        assert result_two["results"][3]["id"] == str(template_four.id)
        assert result_two["results"][3]["sequence"] == "4"

        assert result_two["results"][4]["id"] == str(template_five.id)
        assert result_two["results"][4]["sequence"] == "5"

    def test_template_transition(self):
        """Test transitioning a Templates's status."""
        template_one = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
            **self.workstation_data,
        )
        template_two = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
            **self.workstation_data,
        )

        url = reverse(
            "message-transition", kwargs={"id": template_one.id, "status": "ACTIVE"}
        )
        url_two = reverse(
            "message-transition", kwargs={"id": template_two.id, "status": "ACTIVE"}
        )
        self.client.patch(url)
        self.client.patch(url_two)

        template_one.refresh_from_db()
        assert template_one.status == SegmentMessageStatus.ACTIVE

        logs = MessageTemplateTransitionLog.objects.get(
            message_template_id=template_one.id
        )
        assert logs.message_template.id == template_one.id
        assert logs.status_to == SegmentStatus.ACTIVE
        assert logs.status_from == SegmentStatus.DRAFT

        url = reverse(
            "message-transition", kwargs={"id": template_one.id, "status": "RETIRED"}
        )
        self.client.patch(url)
        url = reverse("messagetemplatetransitionlog-list")

        response = self.client.get(url, **self.headers).json()
        assert response["count"] == 3

        response = self.client.get(
            url + f"?message_template={template_one.id}",
            **self.headers,
        ).json()
        assert response["count"] == 2
        assert response["results"][0]["updated_by_name"] == "John Doe"

    def test_search_sequence_templates(self):
        """Test searching for sequence templates."""
        main_template = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            name="Message One",
            template="Message One",
        )

        template_two = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            parent=main_template,
            name="Message Two",
            template="Message Two",
        )
        template_three = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            parent=template_two,
            name="Message Three",
            template="Message Three",
        )
        template_four = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            parent=template_three,
            name="Message Four",
            template="Message Four",
        )

        baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            parent=template_four,
            name="Message Five",
            template="Message Five",
        )

        url = reverse("messagetemplate-templates", kwargs={"pk": main_template.id})
        search_url = f"{url}?search=Four"

        response = self.client.get(search_url)
        result = response.json()

        assert result["count"] == 1
        assert result["results"][0]["id"] == str(template_four.id)
        assert result["results"][0]["sequence"] == "4"

    def test_message_template_detail(self):
        """Test retrieving a template by id."""
        template_one = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
        )
        template_two = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            parent=template_one,
        )

        url_one = reverse("messagetemplate-detail", kwargs={"pk": template_one.id})
        response_one = self.client.get(url_one)
        assert response_one.status_code == 200

        result_one = response_one.json()
        assert result_one["id"] == str(template_one.id)

        url_two = reverse("messagetemplate-detail", kwargs={"pk": template_two.id})
        response_two = self.client.get(url_two)
        assert response_two.status_code == 200

        result_two = response_two.json()
        assert result_two["id"] == str(template_two.id)

    def test_patch_message_template(self):
        """Test patching a template."""
        template_one = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
        )
        template_two = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            parent=template_one,
        )

        url_one = reverse("messagetemplate-detail", kwargs={"pk": template_one.id})
        response = self.client.get(url_one)
        assert response.status_code == 200

        response = self.client.patch(url_one, {"name": "Things are changing"})
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Things are changing"

        url_two = reverse("messagetemplate-detail", kwargs={"pk": template_two.id})
        response_two = self.client.get(url_two)
        assert response_two.status_code == 200

        response_two = self.client.patch(
            url_two, {"name": "Things are changing too", "parent": str(template_one.id)}
        )
        assert response_two.status_code == 200
        data = response_two.json()
        assert data["name"] == "Things are changing too"

    def test_search_message_template_by_name(self):
        """Test searching a template by name."""
        baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            name="Birthday Template",
            **self.workstation_data,
        )
        url = reverse("messagetemplate-list")

        response = self.client.get(
            url + "?search=Birthday",
            **self.headers,
        ).json()
        assert response["count"] == 1

        response = self.client.get(
            url + "?search=Random",
            **self.headers,
        ).json()
        assert response["count"] == 0

    def test_add_message_to_sequenced_template(self):
        """Test adding a new message template to a sequence."""
        main_template = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            template="Message One",
            **self.workstation_data,
        )

        url = reverse(
            "messagetemplate-add-sequenced-message", kwargs={"pk": main_template.id}
        )

        # add the first message in the sequence
        payload = {
            "name": "Message Two",
            "template": "Hello there!",
            "message_type": "SEQUENCED",
        }
        response_one = self.client.post(url, payload, **self.headers).json()
        assert response_one["name"] == "Message Two"
        assert response_one["parent"] == str(main_template.id)

        # add the second message in the sequence
        payload = {
            "name": "Message Three",
            "template": "Hello there Again!",
            "message_type": "SEQUENCED",
        }
        response_two = self.client.post(url, payload, **self.headers).json()

        assert response_two["name"] == "Message Three"
        assert response_two["parent"] == response_one["id"]

    def test_create_translated_message_template(self):
        """Test create a translated template."""
        url = reverse("messagetemplate-list")

        payload = {
            "name": "Segment Welcome Message",
            "template": "Hi, welcome to this segment!",
            "message_type": "SINGULAR",
        }

        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 201

        result = response.json()
        assert result["template"] == "Hi, welcome to this segment!"
        assert result["template_en"] == "Hi, welcome to this segment!"
        assert result["template_sw"] is None
        assert result["template_fr"] is None

        fr_payload = {
            "name": "Segment Welcome Message",
            "template": "Bonjour, bienvenue dans ce segment!",
            "message_type": "SINGULAR",
        }

        french_headers = {**self.headers, "Accept-Language": "fr"}
        response_two = self.client.post(url, fr_payload, headers=french_headers)
        assert response_two.status_code == 201

        result_two = response_two.json()
        assert result_two["template"] == "Bonjour, bienvenue dans ce segment!"
        assert result_two["template_en"] is None
        assert result_two["template_sw"] is None
        assert result_two["template_fr"] == "Bonjour, bienvenue dans ce segment!"

    def test_list_template_variables(self):
        """Test listing template variables."""
        url = reverse("messagetemplate-variables")

        response = self.client.get(url, headers=self.headers)
        assert response.status_code == 200

        result = response.json()
        assert result[0]["name"] == "Title"
        assert result[0]["variable"] == "{{title}}"

        # test with extra variables
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )

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
        patient_upload = baker.make(
            PatientListUpload,
            upload_file=attachment,
            process_state="COMPLETE",
            upload_type="GENERAL",
            created_by=self.user.guid,
            updated_by=self.user.guid,
            **self.workstation_data,
        )

        baker.make(
            SegmentUpload,
            organisation=self.global_organisation,
            created_by=self.user.id,
            file_upload=patient_upload,
            segment=segment,
            extra_headers=["clinic_name", "tca_date"],
        )

        response_two = self.client.get(
            url + f"?segment_id={segment.id}", headers=self.headers
        )

        result = response_two.json()
        assert result[4]["name"] in ["Clinic Name", "Tca Date"]


@pytest.mark.usefixtures("default_transactional_sender")
class SegmentMessageDeliveryViewsetTestCase(LoggedInMixin):
    """Test message template viewset."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()

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
        self.default_transactional_sender = SenderID.objects.filter(
            name="BeWellApp"
        ).latest("created")

    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_list_segment_message_delivery_logs(self, mock_send_sms):
        """Test listing message delivery logs."""
        baker.make(SILUser, email=settings.SYSTEM_ADMIN_EMAIL)

        person = baker.make(
            Person,
            first_name="Sam",
            last_name="Tabman",
            organisation=self.global_organisation,
        )
        baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254722060000",
        )

        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )

        member = baker.make(
            SegmentMember,
            person=person,
            segment=segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
        )

        template_one = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            status=SegmentMessageStatus.ACTIVE,
        )

        template_two = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            status=SegmentMessageStatus.ACTIVE,
        )
        segment_message = baker.make(
            SegmentMessage,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
            template=template_one,
            segment=segment,
            created_by=self.user.id,
        )

        url = reverse("segmentmessagedelivery-list")

        response = self.client.get(url)
        assert response.status_code == 200
        result = response.json()
        assert result["count"] == 0

        template_one.send_message(
            recipient=member,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
            segment_message=segment_message,
        )
        mock_send_sms.assert_called()

        response_two = self.client.get(url)
        assert response_two.status_code == 200
        result_two = response_two.json()
        assert result_two["count"] == 1

        segment_message_two = baker.make(
            SegmentMessage,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
            template=template_two,
            segment=segment,
            created_by=self.user.id,
        )

        template_two.send_message(
            recipient=member,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
            segment_message=segment_message_two,
        )
        mock_send_sms.assert_called()

        response_three = self.client.get(url)
        assert response_three.status_code == 200
        result_three = response_three.json()
        assert result_three["count"] == 2

        response_three = self.client.get(
            f"{url}?segment_message_id={str(segment_message_two.id)}"
        )
        assert response_three.status_code == 200
        result_three = response_three.json()
        assert result_three["count"] == 1

    def test_list_segment_message_delivery_logs_using_state_filter(self):
        """Test listing message delivery logs using the state filter."""
        person = baker.make(
            Person,
            first_name="Sam",
            last_name="Tabman",
            organisation=self.global_organisation,
        )
        baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254722060000",
        )

        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )

        member = baker.make(
            SegmentMember,
            person=person,
            segment=segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
        )

        template_one = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            status=SegmentMessageStatus.ACTIVE,
        )

        segment_message = baker.make(
            SegmentMessage,
            organisation=self.global_organisation,
            template=template_one,
            segment=segment,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
        )

        sms = baker.make(
            SMS,
            organisation=self.global_organisation,
            sender=self.default_transactional_sender,
            message="Hi there",
            recipients=["+254722060000"],
            intention="BROADCAST",
            state="DELIVERED",
        )

        baker.make(
            SegmentMessageDelivery,
            member=member,
            dispatched_at=timezone.now(),
            message_template=template_one,
            segment_message=segment_message,
            sms=sms,
        )

        url = reverse("segmentmessagedelivery-list")
        response = self.client.get(
            f"{url}?segment_message_id={segment_message.id}&state={sms.state}"
        )
        assert response.status_code == 200
        result = response.json()
        assert result["count"] == 1

    @patch(
        "sil_advantage.segments.tasks.retry_failed_to_send_segment_messages.apply_async"
    )
    def test_get_segment_message_delivery_consolidated_delivery_metrics_report(
        self, mock_retry_failed_segment_messages
    ):
        """Test getting a segment message delivery metrics report."""
        person = baker.make(
            Person,
            first_name="Sam",
            last_name="Tabman",
            organisation=self.global_organisation,
        )
        baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254722060000",
        )

        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )

        # add member to two different segments
        member = baker.make(
            SegmentMember,
            person=person,
            segment=segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        message_template = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        segment_message = baker.make(
            SegmentMessage,
            organisation=self.global_organisation,
            template=message_template,
            segment=segment,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
        )

        sms = baker.make(
            SMS,
            organisation=self.global_organisation,
            sender=self.default_transactional_sender,
            message="Hi there",
            recipients=["+254722060000"],
            intention="BROADCAST",
            state="FAILED",
        )

        baker.make(
            SegmentMessageDelivery,
            member=member,
            dispatched_at=timezone.now(),
            message_template=message_template,
            segment_message=segment_message,
            sms=sms,
        )

        url = reverse("segmentmessagedelivery-consolidated-delivery-metrics")
        response = self.client.get(
            f"{url}?segment_message_id={segment_message.id}&message_id={str(message_template.id)}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["data"][0]["state"] == "FAILED"
        assert result["data"][0]["total"] == 1
        assert result["count"] == 1

        # try making call with missing query params
        response = self.client.get(f"{url}?message_id={str(message_template.id)}")
        data = response.json()
        assert response.status_code == 400
        assert (
            data["error"]
            == "Segment Message ID & Message Template ID must be provided!"
        )

        # try retrying a failed message
        url = reverse("segmentmessagedelivery-retry-failed-segment-messages")
        payload = {
            "segment_message_id": segment_message.id,
            "message_id": message_template.id,
        }
        response = self.client.post(url, payload)
        assert response.status_code == 202
        mock_retry_failed_segment_messages.assert_called_once_with(
            queue="advantage_tasks",
            priority=5,
            args=(str(segment_message.id), str(message_template.id)),
        )

        # try retrying a failed message with missing query params
        payload = {
            "segment_id": segment.id,
        }
        response = self.client.post(url, payload)
        data = response.json()
        assert response.status_code == 400
        assert (
            data["error"]
            == "Segment Message ID & Message Template ID must be provided!"
        )

        # try generating a segment message delivery report
        payload = {
            "segment_message_id": segment_message.id,
            "message_id": message_template.id,
        }
        url = reverse("segmentmessagedelivery-generate-delivery-metrics-report")
        response = self.client.post(url, payload)
        assert response.status_code == 200

        # try making call with missing payload
        payload = {
            "segment_id": segment_message.id,
        }
        response = self.client.post(url, payload)
        data = response.json()
        assert response.status_code == 400
        assert (
            data["error"]
            == "Segment Message ID & Message Template ID must be provided!"
        )

    def test_retrieve_delivery_metrics_with_reused_template(self):
        """Test retrieving delivery metrics with a reused template."""
        person = baker.make(
            Person,
            first_name="Sam",
            last_name="Tabman",
            organisation=self.global_organisation,
        )

        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )
        member = baker.make(
            SegmentMember,
            person=person,
            segment=segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
        )
        template = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            status=SegmentMessageStatus.ACTIVE,
        )

        # reuse template within segment
        segment_message_recipe = recipe.Recipe(
            SegmentMessage,
            organisation=self.global_organisation,
            template=template,
            segment=segment,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
        )
        segment_message_recipe.make(_quantity=2)
        segment_message_qs = SegmentMessage.objects.filter(segment=segment)

        sms_recipe = recipe.Recipe(
            SMS,
            organisation=self.global_organisation,
            sender=self.default_transactional_sender,
            message="Hi there",
            recipients=["+254722060000"],
            intention="BROADCAST",
            state="DELIVERED",
        )
        sms_recipe.make(_quantity=2)
        sms = SMS.objects.filter(organisation=self.global_organisation)

        segment_message_delivery_recipe = recipe.Recipe(
            SegmentMessageDelivery,
            organisation=self.global_organisation,
            member=member,
            dispatched_at=timezone.now(),
            message_template=template,
            sms=cycle(sms),
            segment_message=cycle(segment_message_qs),
        )
        segment_message_delivery_recipe.make(_quantity=2)

        url = reverse("segmentmessagedelivery-consolidated-delivery-metrics")
        response = self.client.get(
            f"{url}?segment_message_id={segment_message_qs[0].id}&message_id={template.id}"
        )
        assert response.status_code == 200
        result = response.json()
        assert result["data"][0]["state"] == "DELIVERED"
        assert result["data"][0]["total"] == 1
        assert result["count"] == 1

    def test_generate_delivery_metrics_report_no_sms_logs(self):
        """Test generate delivery metrics reports with no sms logs."""
        person = baker.make(
            Person,
            first_name="Sam",
            last_name="Tabman",
            organisation=self.global_organisation,
        )

        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )
        baker.make(
            SegmentMember,
            person=person,
            segment=segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
        )
        template = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            status=SegmentMessageStatus.ACTIVE,
        )

        # reuse template within segment
        segment_message = baker.make(
            SegmentMessage,
            organisation=self.global_organisation,
            template=template,
            segment=segment,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
        )

        payload = {
            "segment_message_id": segment_message.id,
        }
        url = reverse("segmentmessagedelivery-generate-delivery-metrics-report")
        response = self.client.post(url, payload)
        assert response.status_code == 400

        payload = {
            "segment_message_id": segment_message.id,
            "message_id": str(uuid.uuid4()),
        }
        url = reverse("segmentmessagedelivery-generate-delivery-metrics-report")
        response = self.client.post(url, payload)
        assert response.status_code == 400

    def test_search_message_recipient_in_delivery_report(self):
        """Test searching message recipient by name."""
        baker.make(SILUser, email=settings.SYSTEM_ADMIN_EMAIL)

        person = baker.make(
            Person,
            first_name="Chris",
            last_name="Chan",
            organisation=self.global_organisation,
            **self.workstation_data,
        )

        baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254722060000",
            **self.workstation_data,
        )

        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            **self.workstation_data,
        )

        member = baker.make(
            SegmentMember,
            person=person,
            segment=segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            **self.workstation_data,
        )

        template = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            **self.workstation_data,
        )

        sms = baker.make(
            SMS,
            organisation=self.global_organisation,
            sender=self.default_transactional_sender,
            message="Hi there",
            recipients=["+254722060000"],
            intention="BROADCAST",
            state="DELIVERED",
            **self.workstation_data,
        )

        baker.make(
            SegmentMessageDelivery,
            member=member,
            dispatched_at=timezone.now(),
            message_template=template,
            sms=sms,
            **self.workstation_data,
        )

        url = reverse("segmentmessagedelivery-list")
        response = self.client.get(
            url + "?search=Chris",
            **self.headers,
        )
        result = response.json()

        assert result["count"] == 1

        url = reverse("segmentmessagedelivery-list")
        response = self.client.get(
            url + "?search=Tim",
            **self.headers,
        )
        result = response.json()

        assert result["count"] == 0


class SegmentMembersViewsetTestCase(LoggedInMixin):
    """Test segment members viewset."""

    def setUp(self):
        """Set up test environment."""
        baker.make(SILUser, email=settings.SYSTEM_ADMIN_EMAIL)

        super().setUp()

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
        self.segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )
        self.person = baker.make(
            Person,
            first_name="Sam",
            last_name="Tabman",
            organisation=self.global_organisation,
        )
        baker.make(
            Consent,
            person=self.person,
            organisation=self.global_organisation,
            consent_type=ConsentType.SMS_COMMUNICATION,
        )
        self.url = reverse("segmentmember-list")

    def test_add_member_to_segment(self):
        """Test adding a member to a segment."""
        payload = {"segment_id": str(self.segment.id), "person_id": str(self.person.id)}

        response = self.client.post(self.url, payload, format="json", **self.headers)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(SegmentMember.objects.count(), 1)
        segment_member = SegmentMember.objects.first()
        self.assertEqual(segment_member.segment.id, self.segment.id)
        self.assertEqual(segment_member.person.id, self.person.id)

        # test list segment memebers
        response = self.client.get(self.url, **self.headers)
        data = response.json()

        assert data["count"] == 1
        assert data["results"][0]["consent_status"] == "PENDING"

    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_list_segment_message_delivery_logs(self, mock_send_sms):
        """Test listing message delivery logs."""
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )

        baker.make(
            SegmentMember,
            person=self.person,
            segment=segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
        )

        person_two = baker.make(
            Person,
            first_name="Sam",
            last_name="Ctrlman",
            organisation=self.global_organisation,
        )

        baker.make(
            SegmentMember,
            person=person_two,
            segment=segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
        )

        response = self.client.get(self.url)
        assert response.status_code == 200
        result = response.json()
        assert result["count"] == 2
        assert result["results"][0]["segment"]["name"] == segment.name

        # filter segments for a single person
        response_two = self.client.get(f"{self.url}?person={str(self.person.id)}")
        assert response_two.status_code == 200
        result = response_two.json()
        assert result["count"] == 1
        assert result["results"][0]["segment"]["name"] == segment.name

    def test_search_members_in_a_segment(self):
        """Test searching members in a segment."""
        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            label="CERVICAL_CANCER_HIGH_RISK",
            **self.workstation_data,
        )
        message = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            created_by=self.user.id,
            **self.workstation_data,
        )
        baker.make(
            SegmentMessage,
            template=message,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
            segment=segment,
            created_by=self.user.id,
        )
        person = baker.make(
            Person,
            first_name="Oscar",
            last_name="Tawe",
            other_names="Ian",
            organisation=self.global_organisation,
            created_by=self.user.id,
            **self.workstation_data,
        )
        baker.make(
            SegmentMember,
            organisation=self.global_organisation,
            created_by=self.user.id,
            segment=segment,
            person=person,
            **self.workstation_data,
        )

        url = reverse("segmentmember-list")

        response = self.client.get(
            url + "?search=Oscar",
            **self.headers,
        )
        result = response.json()

        assert result["count"] == 1
        assert result["results"][0]["person"]["first_name"] == "Oscar"

        response_two = self.client.get(
            url + "?search=Tawe",
            **self.headers,
        )
        result = response_two.json()

        assert result["count"] == 1
        assert result["results"][0]["person"]["last_name"] == "Tawe"

        response_three = self.client.get(
            url + "?search=Ian",
            **self.headers,
        )
        result = response_three.json()

        assert result["count"] == 1
        assert result["results"][0]["person"]["other_names"] == "Ian"

    def test_transition_segment_member(self):
        """Test transitioning a segment members's status."""
        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            updated_by=self.user.id,
            created_by=self.user.id,
        )

        member_one = baker.make(
            SegmentMember,
            person=self.person,
            segment=segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        person_two = baker.make(
            Person,
            first_name="Sam",
            last_name="Ctrlman",
            organisation=self.global_organisation,
        )

        member_two = baker.make(
            SegmentMember,
            person=person_two,
            segment=segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        url = reverse(
            "segment-member-transition",
            kwargs={"id": member_one.id, "status": "RETIRED"},
        )
        url_two = reverse(
            "segment-member-transition",
            kwargs={"id": member_two.id, "status": "RETIRED"},
        )
        self.client.patch(url)
        self.client.patch(url_two)

        member_one.refresh_from_db()
        assert member_one.status == SegmentMemberStatus.RETIRED

        logs = SegmentMemberTransitionLog.objects.get(segment_member=member_one.id)
        assert logs.segment_member.id == member_one.id
        assert logs.status_to == SegmentMemberStatus.RETIRED
        assert logs.status_from == SegmentMemberStatus.CONFIRMED

        url = reverse(
            "segment-member-transition",
            kwargs={"id": member_one.id, "status": "CONFIRMED"},
        )
        self.client.patch(url)

        url = reverse("segmentmembertransitionlog-list")
        response = self.client.get(url, **self.headers).json()
        assert response["count"] == 3

        response = self.client.get(
            url + f"?segment_member={member_one.id}",
            **self.headers,
        ).json()
        assert response["count"] == 2
        assert response["results"][0]["updated_by_name"] == "John Doe"


@pytest.mark.usefixtures("default_transactional_sender")
class SegmentMessageViewsetTestCase(LoggedInMixin):
    """Test segment message viewset."""

    def setUp(self):
        """Set up test environment."""
        baker.make(SILUser, email=settings.SYSTEM_ADMIN_EMAIL)

        super().setUp()

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
        self.default_transactional_sender = SenderID.objects.filter(
            name="BeWellApp"
        ).latest("created")

        self.person = baker.make(
            Person,
            first_name="Sam",
            last_name="Tabman",
            organisation=self.global_organisation,
        )
        self.sender = baker.make(
            SenderID,
            name="BeWellApp",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=90),
        )
        self.segment = baker.make(Segment, organisation=self.global_organisation)
        baker.make(SegmentMember, person=self.person, segment=self.segment)

    def test_create_segment_message_with_sender(self):
        """Test creating a segment message with a provided sender."""
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )
        template = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            name="ANC Segment",
            template="Welcome to this segment",
            created_by=self.user.id,
        )
        sender = self.default_transactional_sender

        payload = {
            "template": template.id,
            "segment": segment.id,
            "sender_id": sender.id,
            "delivery_type": "INSTANT",
            "send_on_segment_join": True,
        }

        url = reverse(
            "segmentmessage-list",
        )
        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 201
        message = SegmentMessage.objects.filter().latest("created")
        assert message.sender.name == "BeWellApp"
        assert message.send_on_segment_join is True

        response = self.client.get(url)
        assert response.status_code == 200

        # test search functionality with name
        response = self.client.get(
            url + "?search=ANC" + f"&segment={segment.id}",
            **self.headers,
        ).json()
        assert response["count"] == 1

        # test search functionality with template
        response = self.client.get(
            url + "?search=Welcome to" + f"&segment={segment.id}",
            **self.headers,
        ).json()
        assert response["count"] == 1

        response = self.client.get(
            url + "?search=Hello there" + f"&segment={segment.id}",
            **self.headers,
        ).json()
        assert response["count"] == 0

    @patch("sil_advantage.segments.views.can_send_sms")
    def test_preview_broadcast_message(
        self,
        mock_can_send_sms,
    ):
        """Test previewing a message before sending to one or more Segments."""
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )
        template = "Hello {{first_name}} {{last_name}}, welcome to this Segment."

        payload = {
            "segment_ids": [segment.id],
            "template": template,
            "delivery_type": "INSTANT",
            "send_on_segment_join": True,
        }
        url = reverse("segmentmessage-preview")

        mock_can_send_sms.return_value = (
            True,
            "",
            1,
            Decimal("100.00"),
            {"bulk_sms_account": {"balance": "100.00"}},
        )

        # Segment has no active members
        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 400
        response_data = response.json()
        assert (
            response_data["non_field_errors"][0]
            == "Segment(s) provided has no active members!"
        )

        # Segment has active members
        baker.make(SegmentMember, person=self.person, segment=segment)
        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "SUFFICIENT_BALANCE"
        assert response_data["balance"] == "100.00"
        assert (
            response_data["message_preview"]
            == "Hello Sam Tabman, welcome to this Segment."
        )

    @patch("sil_advantage.segments.views.can_send_sms")
    def test_preview_broadcast_message_with_template_id(
        self,
        mock_can_send_sms,
    ):
        """Test previewing a message with a provided template_id."""
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )
        template = baker.make(
            MessageTemplate,
            template="Hello {{first_name}} {{last_name}}, welcome to this Segment!",
            organisation=self.global_organisation,
            created_by=self.user.id,
        )

        payload = {
            "segment_ids": [segment.id],
            "template_id": str(template.id),
            "delivery_type": "INSTANT",
            "send_on_segment_join": True,
        }
        url = reverse("segmentmessage-preview")

        mock_can_send_sms.return_value = (True, "", 1, Decimal("100.00"), None)

        baker.make(SegmentMember, person=self.person, segment=segment)

        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 200
        response_data = response.json()

        # Ensure the correct template is used
        assert (
            response_data["message_preview"]
            == "Hello Sam Tabman, welcome to this Segment!"
        )

    @patch("sil_advantage.billing.utils.get_wallet_balances")
    @patch("sil_advantage.common.api_clients.erp.fetch_from_erp_cache")
    def test_preview_broadcast_message_with_sender_id(
        self, mock_fetch_from_erp_cache, mock_get_wallet_balances
    ):
        """Test previewing a message with a provided sender_id."""
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )
        template = "Hello {{first_name}} {{last_name}}, welcome to this Segment."

        # Create a sender to provide sender_id
        sender = baker.make(
            SenderID,
            name="CustomSender",
            organisation=self.global_organisation,
            created_by=self.user.id,
            end_date=timezone.now() + timedelta(days=90),
        )

        payload = {
            "segment_ids": [segment.id],
            "template": template,
            "sender_id": str(sender.id),
            "delivery_type": "INSTANT",
            "send_on_segment_join": True,
        }

        url = reverse("segmentmessage-preview")

        mock_get_wallet_balances.return_value = {
            "bulk_sms_account": {"balance": Decimal("100.00")}
        }
        mock_fetch_from_erp_cache.side_effect = [
            {"id": "sil_org_id"},
            {"results": [{"rate": "1.00"}]},
        ]

        baker.make(SegmentMember, person=self.person, segment=segment)

        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 200
        response_data = response.json()

        # Ensure the sender name is fetched correctly
        assert response_data["sender"] == "CustomSender"
        assert (
            response_data["message_preview"]
            == "Hello Sam Tabman, welcome to this Segment."
        )

    def test_send_broadcast_with_existing_template(self):
        """Test sending a broadcast to a segment(s) with existing template."""
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )

        template = baker.make(
            MessageTemplate,
            template="Hello! welcome to this segment",
            organisation=self.global_organisation,
            created_by=self.user.id,
        )
        baker.make(SegmentMember, person=self.person, segment=segment)
        payload = {
            "segment_ids": [segment.id],
            "sender_id": self.default_transactional_sender.id,
            "template_id": template.id,
            "delivery_type": "INSTANT",
            "send_on_segment_join": True,
        }

        url = reverse(
            "segmentmessage-send-sms",
        )
        response = self.client.post(url, payload)
        assert response.status_code == 201
        response_data = response.json()
        assert response_data["template_id"] == str(template.id)

        # try sending with missing segment(s)
        payload.pop("segment_ids")
        response = self.client.post(url, payload)

        data = response.json()
        assert response.status_code == 400
        assert data["segment_ids"][0] == "This field is required."

        # try sending broadcast with missing template
        payload.pop("template_id")
        payload["segment_ids"] = [segment.id]

        response = self.client.post(url, payload)
        data = response.json()
        assert response.status_code == 400
        assert (
            data["non_field_errors"][0]
            == "Either Template ID or Template Object should be provided!"
        )

        # try sending broadcast with multiple templates
        payload["template_id"] = template.id
        payload["template"] = "Happy Birthday!"

        response = self.client.post(url, payload)
        data = response.json()
        assert response.status_code == 400
        assert (
            data["non_field_errors"][0]
            == "Either Template ID or Template Object should be provided!"
        )

    def test_send_broadcast_with_new_template(self):
        """Test sending a broadcast to a segment(s) with a new template."""
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )
        baker.make(SegmentMember, person=self.person, segment=segment)

        payload = {
            "segment_ids": [segment.id],
            "sender_id": self.default_transactional_sender.id,
            "template": "Happy Birthday!",
            "delivery_type": "SCHEDULED_RECURRENT",
            "scheduled_at": "2050-07-15T10:30:00Z",
            "sequence_interval": "5 4 * * 1",
            "send_on_segment_join": True,
        }
        url = reverse(
            "segmentmessage-send-sms",
        )

        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 201
        response_data = response.json()
        assert response_data["segments"][0]["segment_id"] == str(segment.id)

        template_id = response_data["template_id"]
        template = MessageTemplate.objects.get(id=template_id)
        assert template.status == SegmentMessageStatus.ACTIVE

        # try sending a one-time scheduled message
        payload.pop("sequence_interval")
        payload["delivery_type"] = "SCHEDULED_ONE_TIME"

        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 201

        # try sending a one-time scheduled message missing schedule
        payload.pop("scheduled_at")
        payload["delivery_type"] = "SCHEDULED_ONE_TIME"

        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 400
        data = response.json()
        assert (
            data["non_field_errors"][0]
            == "Schedule should be provided for a scheduled message!"
        )

        # try sending a scheduled recurrent message with missing schedule and interval
        payload["delivery_type"] = "SCHEDULED_RECURRENT"

        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 400
        data = response.json()
        assert (
            data["non_field_errors"][0]
            == "Interval should be provided for a scheduled recurrent message!"  # noqa: B950
        )

    @patch("sil_advantage.billing.utils.get_wallet_balances")
    @patch("sil_advantage.common.api_clients.erp.fetch_from_erp_cache")
    def test_check_sms_balance_with_new_template(
        self, mock_fetch_from_erp_cache, mock_get_wallet_balances
    ):
        """Test checking SMS wallet balance with new template."""
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )
        baker.make(SegmentMember, segment=segment, _quantity=10)
        template = "Hello! Welcome to our service."

        payload = {
            "segment_ids": [str(segment.id)],
            "template": template,
            "delivery_type": "INSTANT",
            "send_on_segment_join": True,
        }

        url = reverse("segmentmessage-check-sms-balance")

        # Sufficient balance
        mock_get_wallet_balances.return_value = {
            "bulk_sms_account": {"balance": Decimal("100.00")}
        }

        mock_fetch_from_erp_cache.side_effect = [
            {"id": "sil_org_id"},
            {"results": [{"rate": "1.00"}]},
        ]

        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUFFICIENT_BALANCE"
        assert data["message"] == "Sufficient balance available"

        # Insufficient balance
        mock_get_wallet_balances.return_value = {
            "bulk_sms_account": {"balance": Decimal("0.00")}
        }

        mock_fetch_from_erp_cache.side_effect = [
            {"id": "sil_org_id"},
            {"results": [{"rate": "1.00"}]},
        ]

        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "INSUFFICIENT_BALANCE"
        assert data["detail"] == (
            "Low wallet balance. Please top up your wallet to continue sending "
            "messages."
        )

    @patch("sil_advantage.billing.utils.get_wallet_balances")
    @patch("sil_advantage.common.api_clients.erp.fetch_from_erp_cache")
    def test_check_sms_balance_with_existing_template(
        self, mock_fetch_from_erp_cache, mock_get_wallet_balances
    ):
        """Test checking SMS wallet balance with existing template."""
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )
        template = baker.make(
            MessageTemplate,
            organisation=self.global_organisation,
            template="Hello! Welcome to our service.",
            created_by=self.user.id,
        )
        baker.make(SegmentMember, segment=segment, _quantity=10)

        payload = {
            "segment_ids": [str(segment.id)],
            "template_id": str(template.id),
            "delivery_type": "INSTANT",
            "send_on_segment_join": True,
        }
        url = reverse("segmentmessage-check-sms-balance")

        # Sufficient balance
        mock_get_wallet_balances.return_value = {
            "bulk_sms_account": {"balance": Decimal("100.00")}
        }

        mock_fetch_from_erp_cache.side_effect = [
            {"id": "sil_org_id"},
            {"results": [{"rate": "1.00"}]},
        ]

        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUFFICIENT_BALANCE"
        assert data["message"] == "Sufficient balance available"

        # Insufficient balance
        mock_get_wallet_balances.return_value = {
            "bulk_sms_account": {"balance": Decimal("0.00")}
        }

        mock_fetch_from_erp_cache.side_effect = [
            {"id": "sil_org_id"},
            {"results": [{"rate": "1.00"}]},
        ]

        response = self.client.post(url, payload, **self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "INSUFFICIENT_BALANCE"
        assert data["detail"] == (
            "Low wallet balance. Please top up your wallet to continue sending "
            "messages."
        )


class FilterViewSetTestCase(LoggedInMixin):
    """Test Filter viewset."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        baker.make(SILUser, email="network.admin@slade360.co.ke")

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

    def test_list_filters(self):
        """Test listing available filters."""
        baker.make(
            Filter,
            name="Gender",
            allowed_operations=["EQUALS"],
            choice_source=FilterChoiceSource.CLOSE_ENDED_CHOICES,
            close_ended_choices=[
                {"name": "Male", "value": "MALE"},
                {"name": "Female", "value": "FEMALE"},
            ],
        )

        url = reverse("filter-list")
        response = self.client.get(url)

        assert response.status_code == 200

    def test_list_filter_close_ended_choices(self):
        """Test listing available filters."""
        filter = baker.make(
            Filter,
            name="Gender",
            allowed_operations=["EQUALS"],
            choice_source=FilterChoiceSource.CLOSE_ENDED_CHOICES,
            close_ended_choices=[
                {"name": "Male", "value": "MALE"},
                {"name": "Female", "value": "FEMALE"},
            ],
        )

        url = reverse("filter-choices", kwargs={"pk": str(filter.id)})
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data["count"] == 2
        assert data["results"][0]["name"] == "Male"
        assert data["results"][0]["value"] == "MALE"

    def test_list_filter_ocl_choices(self):
        """Test listing available filters."""
        filter = baker.make(
            Filter,
            name="Gender",
            allowed_operations=["EQUALS"],
            choice_source=FilterChoiceSource.OCL,
        )

        url = reverse("filter-choices", kwargs={"pk": str(filter.id)})
        response = self.client.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data["count"] == 0

    def test_create_filter(self):
        """Test creating a valid filter."""
        payload = {
            "name": "Gender",
            "source": "CLINICAL",
            "allowed_operations": ["EQUALS"],
            "value_type": "CLOSE_ENDED",
            "value_data_type": "STRING",
            "choice_source": "CLOSE_ENDED_CHOICES",
            "display_type": "DROPDOWN",
        }

        url = reverse("filter-list")
        response = self.client.post(url, payload)
        assert response.status_code == 400
        assert "Close ended choices must be provided" in str(response.json())

        payload["close_ended_choices"] = [
            {"name": "Male", "value": "MALE"},
            {"name": "Female", "value": "FEMALE"},
        ]
        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 201

        self.assertEqual(Filter.objects.count(), 1)

    def test_create_filter_with_missing_name(self):
        """Test creating a filter without a name."""
        payload = {
            "source": "CLINICAL",
            "allowed_operations": ["EQUALS"],
            "value_type": "CLOSE_ENDED",
            "value_data_type": "STRING",
            "choice_source": "CLOSE_ENDED_CHOICES",
            "display_type": "DROPDOWN",
        }

        url = reverse("filter-list")
        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 400

    def test_unique_name_constraint(self):
        """Test creating filters with the same name."""
        choices = [
            {"name": "Male", "value": "MALE"},
            {"name": "Female", "value": "FEMALE"},
        ]

        baker.make(
            Filter,
            name="Gender",
            allowed_operations=["EQUALS"],
            choice_source=FilterChoiceSource.CLOSE_ENDED_CHOICES,
            close_ended_choices=choices,
        )

        payload = {
            "name": "Gender",
            "source": "CLINICAL",
            "allowed_operations": ["EQUALS"],
            "value_type": "CLOSE_ENDED",
            "value_data_type": "STRING",
            "choice_source": "CLOSE_ENDED_CHOICES",
            "display_type": "DROPDOWN",
            "close_ended_choices": choices,
        }

        url = reverse("filter-list")
        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 400

    def test_retrieve_filter(self):
        """Test retrieve filter using its ID."""
        filter_obj = baker.make(
            Filter,
            name="Gender",
            allowed_operations=["EQUALS"],
            choice_source=FilterChoiceSource.CLOSE_ENDED_CHOICES,
            close_ended_choices=[
                {"name": "Male", "value": "MALE"},
                {"name": "Female", "value": "FEMALE"},
            ],
        )

        url = reverse("filter-detail", kwargs={"pk": str(filter_obj.id)})
        response = self.client.get(url, headers=self.headers)
        assert response.status_code == 200
        assert response.data["name"] == filter_obj.name

    def test_retrieve_non_existent_filter(self):
        """Test retrieving a non-existent filter."""
        url = reverse("filter-detail", args=["invalid-id"])
        response = self.client.get(url, headers=self.headers)
        assert response.status_code == 404

    def test_update_filter(self):
        """Test updating a filter."""
        choices = [
            {"name": "Male", "value": "MALE"},
            {"name": "Female", "value": "FEMALE"},
        ]

        filter_obj = baker.make(
            Filter,
            name="Gender",
            allowed_operations=["EQUALS"],
            choice_source=FilterChoiceSource.CLOSE_ENDED_CHOICES,
            close_ended_choices=choices,
        )

        payload = {
            "name": "Updated Gender",
            "source": "CLINICAL",
            "allowed_operations": ["EQUALS"],
            "value_type": "CLOSE_ENDED",
            "value_data_type": "STRING",
            "choice_source": "CLOSE_ENDED_CHOICES",
            "display_type": "DROPDOWN",
            "close_ended_choices": choices,
        }
        url = reverse("filter-detail", kwargs={"pk": str(filter_obj.id)})

        response = self.client.patch(url, payload, headers=self.headers)
        assert response.status_code == 200
        filter_obj.refresh_from_db()
        assert filter_obj.name == "Updated Gender"

    def test_delete_filter(self):
        """Test deleting a filter."""
        filter_obj = baker.make(
            Filter,
            name="Gender",
            allowed_operations=["EQUALS"],
            choice_source=FilterChoiceSource.CLOSE_ENDED_CHOICES,
            close_ended_choices=[
                {"name": "Male", "value": "MALE"},
                {"name": "Female", "value": "FEMALE"},
            ],
        )
        self.assertEqual(Filter.objects.count(), 1)

        url = reverse("filter-detail", kwargs={"pk": str(filter_obj.id)})
        response = self.client.delete(url, headers=self.headers)
        assert response.status_code == 204
        self.assertEqual(Filter.objects.count(), 0)


class FilterGroupViewSetTestCase(LoggedInMixin):
    """Test Filter Group viewset."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        baker.make(SILUser, email="network.admin@slade360.co.ke")

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

    def test_list_filters_group(self):
        """Test listing available filter groups."""
        baker.make(
            FilterGroup,
            name="Filter Group 1",
            **self.workstation_data,
        )

        url = reverse("filtergroup-list")
        response = self.client.get(url)

        assert response.status_code == 200

    def test_create_filter_group(self):
        """Test creating filter groups."""
        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            label="CERVICAL_CANCER_HIGH_RISK",
        )

        url = reverse("filtergroup-list")
        payload = {
            "name": "Filter Group 2",
            "segment": str(segment.id),
        }

        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 201
        self.assertEqual(FilterGroup.objects.count(), 1)

    def test_create_filter_group_with_invalid_segment(self):
        """Test creating a filter group with an invalid segment."""
        payload = {
            "name": "Invalid Filter Group",
            "segment": "invalid-segment-id",
        }

        url = reverse("filtergroup-list")
        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 400

    def test_retrieve_filter_group(self):
        """Test retrieving a filter group."""
        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            label="CERVICAL_CANCER_HIGH_RISK",
            **self.workstation_data,
        )

        filter_group = baker.make(
            FilterGroup,
            name="Filter Group 1",
            segment=segment,
            **self.workstation_data,
        )

        url = reverse("filtergroup-detail", kwargs={"pk": str(filter_group.id)})
        response = self.client.get(url, headers=self.headers)
        assert response.status_code == 200
        assert response.data["name"] == filter_group.name

    def test_delete_filter_group(self):
        """Test deleting a filter group."""
        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            label="CERVICAL_CANCER_HIGH_RISK",
            **self.workstation_data,
        )

        filter_group = baker.make(
            FilterGroup,
            name="Filter Group 1",
            segment=segment,
            **self.workstation_data,
        )
        self.assertEqual(FilterGroup.objects.count(), 1)

        url = reverse("filtergroup-detail", kwargs={"pk": str(filter_group.id)})
        response = self.client.delete(url, headers=self.headers)
        assert response.status_code == 204
        self.assertEqual(FilterGroup.objects.count(), 0)


class FilterGroupFilterViewSetTestCase(LoggedInMixin):
    """Test Filter Group viewset."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        baker.make(SILUser, email="network.admin@slade360.co.ke")

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

    def test_create_filter_group_filter(self):
        """Test creating filter group filter."""
        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            label="CERVICAL_CANCER_HIGH_RISK",
        )

        filter = baker.make(
            Filter,
            name="Gender",
            allowed_operations=["EQUALS"],
            choice_source=FilterChoiceSource.CLOSE_ENDED_CHOICES,
            close_ended_choices=[
                {"name": "Male", "value": "MALE"},
                {"name": "Female", "value": "FEMALE"},
            ],
        )

        filter_group = baker.make(
            FilterGroup,
            segment=segment,
        )

        url = reverse("filtergroupfilter-list")
        payload = {
            "name": "Gender",
            "filter_group": str(filter_group.id),
            "filter_id": str(filter.id),
            "operation": "EQUALS",
            "value": "Female",
        }

        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 201
        self.assertEqual(FilterGroupFilter.objects.count(), 1)

    def test_create_filter_group_filter_with_invalid_operation(self):
        """Test creating a filter group filter with an invalid operation."""
        segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            label="CERVICAL_CANCER_HIGH_RISK",
        )

        filter_obj = baker.make(
            Filter,
            name="Gender",
            allowed_operations=["EQUALS"],
            choice_source=FilterChoiceSource.CLOSE_ENDED_CHOICES,
            close_ended_choices=[
                {"name": "Male", "value": "MALE"},
                {"name": "Female", "value": "FEMALE"},
            ],
        )

        filter_group = baker.make(
            FilterGroup,
            segment=segment,
        )

        url = reverse("filtergroupfilter-list")
        payload = {
            "filter_group": str(filter_group.id),
            "filter_id": str(filter_obj.id),
            "operation": "INVALID_OPERATION",
            "value": "Female",
        }

        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 400


class FilterGroupListViewSetTestCase(LoggedInMixin):
    """Test listing filter groups for a segment."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()

        self.headers = {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

        self.segment = baker.make(
            Segment,
            name="Segmentica",
            description="This is a test segment",
            status="ACTIVE",
        )

        self.filter_group1 = baker.make(
            FilterGroup,
            name="Filter Group 1",
            segment=self.segment,
        )

        self.filter_group2 = baker.make(
            FilterGroup,
            name="Filter Group 2",
            segment=self.segment,
        )

    def test_list_filter_groups_by_segment(self):
        """Test listing filter groups by segment."""
        url = reverse("filtergroup-list")

        response = self.client.get(
            url,
            {"segment_id": str(self.segment.id)},
            **{
                "HTTP_X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
                "HTTP_X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
                "HTTP_X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
                "HTTP_X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["count"] == 2
        assert data["results"][0]["name"] == "Filter Group 2"
        assert data["results"][1]["name"] == "Filter Group 1"


class UpdateSegmentFiltersViewTest(LoggedInMixin):
    """Test update segment filters view."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()

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

        self.segment = baker.make(
            Segment,
            organisation=self.global_organisation,
            created_by=self.user.id,
            filter_execution_status=FilterExecutionStatus.PENDING,
        )

        self.url = reverse("update-segment-filters", args=[self.segment.id])

    @patch.object(CubeJS, "api_call")
    @patch.object(CubeJS, "get_access_token")
    @patch("sil_advantage.segments.tasks.execute_segment_filter_cube_query.apply_async")
    def test_update_segment_filters_success(
        self, mock_execute_segment_filter_query, mock_cube_login, mock_cube_api_call
    ):
        """Test updating segment filters."""
        response = self.client.post(self.url, {})

        self.segment.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Segment filters update initiated.")

        mock_execute_segment_filter_query.assert_called_once_with(
            queue="advantage_tasks",
            priority=5,
            args=(str(self.segment.id),),
        )


class JourneyViewsetTestCase(LoggedInMixin):
    """Test Journey view."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        baker.make(SILUser, email="network.admin@slade360.co.ke")

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

    def test_create_journey_successfully(self):
        """Test creating a journey successfully."""
        url = reverse("journey-list")

        payload = {
            "name": "ANC Mothers",
            "description": "A journey belonging to mothers expecting a baby.",
        }
        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "ANC Mothers"

        response = self.client.get(url + "?search=ANC", headers=self.headers)
        assert response.data["count"] == 1

        # create journey with filters
        filter_one = baker.make(
            Filter,
            name="Gender",
            allowed_operations=[FilterAllowedOperations.EQUALS],
            value_type=FilterValueType.CLOSE_ENDED,
            cube_config={
                "member": "patients_poc.gender",
            },
        )

        payload = {
            "name": "PNC Fathers",
            "journey_attributes": [
                {
                    "filter_id": str(filter_one.id),
                    "operation": "EQUALS",
                    "value": "MALE",
                },
            ],
        }

        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 201

        assert JourneyAttributes.objects.all().count() == 1


class JourneySegmentViewsetTestCase(LoggedInMixin):
    """Test Journey view."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        baker.make(SILUser, email="network.admin@slade360.co.ke")

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

    def test_create_journey_segment_successfully(self):
        """Test creating a journey successfully."""
        url = reverse("journeysegment-list")
        journey = baker.make(
            Journey,
            name="ANC Mothers",
            description="Journey belonging to expectant mothers",
            organisation=self.global_organisation,
        )
        segment = baker.make(
            Segment, organisation=self.global_organisation, created_by=self.user.id
        )

        payload = {
            "journey": journey.id,
            "segment": segment.id,
        }
        response = self.client.post(url, payload, headers=self.headers)
        assert response.status_code == 201

        # list journey segments
        response = self.client.get(url + f"?journey={journey.id}", headers=self.headers)
        assert response.status_code == 200
        assert response.data["count"] == 1
