"""Test Patient related tasks."""
import os
from unittest.mock import patch

import pytest
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from model_bakery import baker

from sil_advantage.common.models.common_models import (
    Attachment,
    Person,
    PersonContact,
)
from sil_advantage.notifications.sms.models import SenderID
from sil_advantage.patients.models import Patient, PatientListUpload
from sil_advantage.patients.tasks import (
    process_patient_list_upload,
    send_patient_communication_consent_otp_sms,
)
from sil_advantage.segments.models import Segment, SegmentMember
from sil_advantage.segments.models.segments import SegmentUpload
from sil_advantage.sil_auth.models import SILUser
from tests.common.test_common_views import global_organisation


class PatientTasksTest(TestCase):
    """Test Patient related tasks."""

    def setUp(self):
        """Test setup for this view."""
        self.user = baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.workstation_data = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }
        self.organisation = global_organisation()

    def test_process_patient_list_upload(self):
        """Test processing a patient list upload file."""
        assets_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "assets")
        )
        data = File(open(assets_dir + "/Test Patient Records.xlsx", "rb"))
        file = SimpleUploadedFile(
            "Test Patient Records.xlsx",
            data.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        mappings = {
            "first_name": "",
            "last_name": "",
            "full_name": "PATIENT NAME",
            "other_names": "",
            "age": "AGE",
            "gender": "GENDER",
            "date_of_birth": "",
            "phone_number": "PHONE NUMBER",
            "patient_number": "",
        }

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
        patient_list = baker.make(
            PatientListUpload,
            upload_file=attachment,
            mapping=mappings,
            process_state="IN_PROGRESS",
            upload_type="GENERAL",
            created_by=self.user.guid,
            updated_by=self.user.guid,
            **self.workstation_data,
        )

        process_patient_list_upload(patient_list.id)

        patient_list.refresh_from_db()
        assert patient_list.success_count == 5
        assert patient_list.fail_count == 0

        patients = Patient.objects.all()
        assert patients.count() == 5
        assert patients.first().source == "UPLOAD"

    def test_process_patient_list_upload_with_failed_record(self):
        """Test processing a patient list upload file with fails."""
        person = baker.make(
            Person,
            first_name="James",
            last_name="Field",
            organisation=self.organisation,
        )
        baker.make(
            PersonContact,
            contact="+254722385672",
            contact_type="phone_number",
            person=person,
            organisation=self.organisation,
        )

        assets_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "assets")
        )
        data = File(open(assets_dir + "/Test Patient Records 2.xlsx", "rb"))
        file = SimpleUploadedFile(
            "Test Patient Records 2.xlsx",
            data.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        mappings = {
            "first_name": "FIRST NAME",
            "last_name": "LAST NAME",
            "full_name": "",
            "other_names": "OTHER NAMES",
            "age": "",
            "gender": "GENDER",
            "date_of_birth": "DOB",
            "phone_number": "PHONE NUMBER",
            "patient_number": "",
        }

        attachment = baker.make(
            Attachment,
            content_type=file.content_type,
            data=file,
            title=file.name,
            size=file.size,
            created_by=self.user.guid,
            updated_by=self.user.guid,
            organisation=self.organisation,
            **self.workstation_data,
        )
        patient_list_upload = baker.make(
            PatientListUpload,
            upload_file=attachment,
            mapping=mappings,
            process_state="IN_PROGRESS",
            upload_type="GENERAL",
            created_by=self.user.guid,
            updated_by=self.user.guid,
            organisation=self.organisation,
            **self.workstation_data,
        )

        process_patient_list_upload(patient_list_upload.id)

        patient_list_upload.refresh_from_db()
        assert patient_list_upload.success_count == 3
        assert patient_list_upload.fail_count == 3

        patients = Patient.objects.all()
        assert patients.count() == 3

    def test_process_patient_list_upload_for_segment(self):
        """Test processing patient list upload for a segment."""
        assets_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "assets")
        )
        data = File(open(assets_dir + "/Test Patient Records.xlsx", "rb"))
        file = SimpleUploadedFile(
            "Test Patient Records.xlsx",
            data.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        mappings = {
            "first_name": "",
            "last_name": "",
            "full_name": "PATIENT NAME",
            "other_names": "",
            "age": "AGE",
            "gender": "GENDER",
            "date_of_birth": "",
            "phone_number": "PHONE NUMBER",
            "patient_number": "",
        }

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
        patient_list = baker.make(
            PatientListUpload,
            upload_file=attachment,
            mapping=mappings,
            process_state="IN_PROGRESS",
            upload_type="SEGMENT",
            created_by=self.user.guid,
            updated_by=self.user.guid,
            **self.workstation_data,
        )
        segment = baker.make(
            Segment,
            organisation=self.organisation,
            created_by=self.user.id,
            label="CERVICAL_CANCER_HIGH_RISK",
        )
        segment_upload = baker.make(
            SegmentUpload,
            segment=segment,
            file_upload=patient_list,
            created_by=self.user.guid,
        )

        process_patient_list_upload(
            patient_list.id, segment_upload_id=segment_upload.id
        )

        patient_list.refresh_from_db()
        assert patient_list.success_count == 5
        assert patient_list.fail_count == 0

        segment.refresh_from_db()
        assert SegmentMember.objects.filter(segment=segment).count() == 5

    def test_process_patient_list_upload_for_segment_no_extra_data(self):
        """Test processing patient list upload for a segment."""
        assets_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "assets")
        )
        data = File(open(assets_dir + "/Test Patient Records 3.xlsx", "rb"))
        file = SimpleUploadedFile(
            "Test Patient Records.xlsx",
            data.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        mappings = {
            "full_name": "PATIENT NAME",
            "age": "AGE",
            "gender": "GENDER",
            "phone_number": "PHONE NUMBER",
        }

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
        patient_list = baker.make(
            PatientListUpload,
            upload_file=attachment,
            mapping=mappings,
            process_state="IN_PROGRESS",
            upload_type="SEGMENT",
            created_by=self.user.guid,
            updated_by=self.user.guid,
            **self.workstation_data,
        )
        segment = baker.make(
            Segment,
            organisation=self.organisation,
            created_by=self.user.id,
            label="CERVICAL_CANCER_HIGH_RISK",
        )
        segment_upload = baker.make(
            SegmentUpload,
            segment=segment,
            file_upload=patient_list,
            created_by=self.user.guid,
        )

        process_patient_list_upload(
            patient_list.id, segment_upload_id=segment_upload.id
        )

        patient_list.refresh_from_db()
        assert patient_list.success_count == 5
        assert patient_list.fail_count == 0

        segment.refresh_from_db()
        assert SegmentMember.objects.filter(segment=segment).count() == 5

    def test_process_patient_list_upload_for_segment_with_already_existing_patient(
        self,
    ):
        """Test processing patient list upload for a segment."""
        person = baker.make(
            Person,
            first_name="Jane",
            last_name="Doe",
            organisation=self.organisation,
        )
        baker.make(
            PersonContact,
            contact="+254712345678",
            contact_type="phone_number",
            person=person,
            organisation=self.organisation,
        )

        assets_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "assets")
        )
        data = File(open(assets_dir + "/Test Patient Records 2.xlsx", "rb"))
        file = SimpleUploadedFile(
            "Test Patient Records 2.xlsx",
            data.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        mappings = {
            "first_name": "FIRST NAME",
            "last_name": "LAST NAME",
            "other_names": "OTHER NAMES",
            "gender": "GENDER",
            "date_of_birth": "DOB",
            "phone_number": "PHONE NUMBER",
        }

        attachment = baker.make(
            Attachment,
            data=file,
            size=file.size,
            title=file.name,
            content_type=file.content_type,
            organisation=self.organisation,
            created_by=self.user.guid,
            updated_by=self.user.guid,
            **self.workstation_data,
        )
        patient_list = baker.make(
            PatientListUpload,
            upload_file=attachment,
            mapping=mappings,
            upload_type="SEGMENT",
            process_state="IN_PROGRESS",
            organisation=self.organisation,
            created_by=self.user.guid,
            updated_by=self.user.guid,
            **self.workstation_data,
        )
        segment = baker.make(
            Segment,
            created_by=self.user.id,
            organisation=self.organisation,
            label="CERVICAL_CANCER_HIGH_RISK",
        )

        segment_upload = baker.make(
            SegmentUpload,
            segment=segment,
            file_upload=patient_list,
            created_by=self.user.guid,
        )

        baker.make(
            SegmentMember, person=person, segment=segment, created_by=self.user.guid
        )

        process_patient_list_upload(
            patient_list.id, segment_upload_id=segment_upload.id
        )

        patient_list.refresh_from_db()
        assert patient_list.success_count == 3
        assert patient_list.fail_count == 3

        assert SegmentMember.objects.filter(segment=segment).count() == 4

    @pytest.mark.usefixtures("default_transactional_sender")
    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_send_patient_communication_consent_otp_sms(self, mock_send_sms):
        """Test sending a patient communication consent otp sms."""
        person = baker.make(
            Person,
            first_name="James",
            last_name="Field",
            organisation=self.organisation,
            **self.workstation_data,
        )

        baker.make(
            PersonContact,
            contact="+254722385672",
            contact_type="phone_number",
            person=person,
            organisation=self.organisation,
        )
        default_transactional_sender = SenderID.objects.filter(name="BeWellApp").latest(
            "created"
        )

        send_patient_communication_consent_otp_sms(
            person.id, "PATIENT_COMMUNICATION_CONSENT_OTP", 546234
        )

        mock_send_sms.assert_called_once_with(
            queue="advantage_tasks",
            priority=5,
            args=(
                "PATIENT_COMMUNICATION_CONSENT_OTP",
                (
                    f"Hi {person.first_name}, "
                    f"your OTP for {self.organisation.organisation_name} "
                    f"communication consent is {546234}."
                ),
                ["+254722385672"],
                self.organisation.slade_code,
                person.branch_id,
                person.workstation_id,
            ),
            kwargs={"sender_id": default_transactional_sender.id},
        )
        # send to a patient without a contact
        contact = PersonContact.objects.filter(person=person)
        contact.delete()

        mock_send_sms.reset_mock()
        send_patient_communication_consent_otp_sms(
            person.id, "PATIENT_COMMUNICATION_CONSENT_OTP", 546234
        )
        mock_send_sms.assert_not_called()
