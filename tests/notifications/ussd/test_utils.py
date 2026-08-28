"""Test USSD utils."""
import uuid
from unittest.mock import patch

from model_bakery import baker

from sil_advantage.common.models import Person, PersonContact
from sil_advantage.common.models.common_models import OperatingRegion
from sil_advantage.notifications.models import USSDCode
from sil_advantage.notifications.ussd.managers.patient_manager import (
    PatientManager,
)
from sil_advantage.notifications.ussd.managers.segment_manager import (
    SegmentManager,
)
from sil_advantage.patients.models import Patient
from sil_advantage.segments.models import Segment, SegmentMember
from sil_advantage.sil_auth.models import SILUser
from tests.common.test_common_views import LoggedInMixin


class TestUSSDStateMachine(LoggedInMixin):
    """Test for ussd state machine."""

    def setUp(self):
        """Setup test environment."""
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.org = self.global_organisation
        self.ussd_code = USSDCode.objects.create(
            ussd_code="*123#",
            gateway="SAFARICOM",
            type="PREPAID",
            organisation=self.org,
            created_by=uuid.uuid4(),
            updated_by=uuid.uuid4(),
        )

    def test_create_patient_success(self):
        """Test create patient successfully."""
        self.region = baker.make(
            OperatingRegion,
            name="Nairobi",
            organisation=self.org,
            unit_type="COUNTY",
        )

        result = PatientManager.create_patient(
            first_name="John",
            last_name="Doe",
            date_of_birth="01/01/2000",
            gender="1",
            phone_number="+254712345678",
            consent_status="VERIFIED",
            ussd_code="*123#",
            associated_region="Nairobi",
            language="en",
        )

        self.assertTrue(result)
        self.assertEqual(Person.objects.count(), 1)
        self.assertEqual(PersonContact.objects.count(), 1)
        self.assertEqual(Patient.objects.count(), 1)
        person = Person.objects.first()
        self.assertEqual(person.first_name, "John")
        self.assertEqual(person.last_name, "Doe")
        self.assertEqual(person.associated_region.name, "Nairobi")

    def test_create_patient_without_region(self):
        """Test creating a patient without an associated region."""
        result = PatientManager.create_patient(
            first_name="Jane",
            last_name="Doe",
            date_of_birth="01/01/2000",
            gender="1",
            phone_number="+254712345678",
            consent_status="VERIFIED",
            ussd_code="*123#",
            language="en",
            associated_region="",
        )

        self.assertTrue(result)
        self.assertEqual(Person.objects.count(), 1)
        person = Person.objects.first()
        self.assertIsNone(person.associated_region)
        self.assertEqual(person.first_name, "Jane")
        self.assertEqual(person.last_name, "Doe")

    def test_create_patient_missing_first_name(self):
        """Test creating a patient missing first name."""
        with self.assertRaises(
            RuntimeError, msg="Error creating patient: value is required"
        ):
            PatientManager.create_patient(
                first_name="",
                last_name="Doe",
                date_of_birth="01/01/2000",
                gender="1",
                phone_number="+254712345678",
                consent_status="VERIFIED",
                ussd_code="*123#",
                associated_region="Nairobi",
                language="en",
            )
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(PersonContact.objects.count(), 0)
        self.assertEqual(Patient.objects.count(), 0)

    @patch("sil_advantage.notifications.ussd.managers.patient_manager.Person.save")
    def test_create_patient_save_failure(self, mock_save):
        """Test creating a patient when the save method fails."""
        self.region = baker.make(
            OperatingRegion,
            name="Nairobi",
            organisation=self.org,
            unit_type="COUNTY",
        )

        mock_save.side_effect = Exception("Database Save Error")

        with self.assertRaises(
            RuntimeError, msg="Error creating Person: Database Save Error"
        ):
            PatientManager.create_person(
                first_name="John",
                last_name="Doe",
                date_of_birth="01/01/2000",
                gender="1",
                phone_number="+254712345678",
                consent_status="VERIFIED",
                code=self.ussd_code,
                associated_region="Nairobi",
                language="sw",
            )

        self.assertEqual(Person.objects.count(), 0)

    def test_opt_out_patient(self):
        """Test opting out a patient."""
        super().setUp()
        person = baker.make(
            Person,
            first_name="Bob",
            last_name="Williamns",
            organisation=self.org,
        )
        patient = baker.make(
            Patient,
            person=person,
            organisation=person.organisation,
        )
        person_contact = baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254790360360",
        )
        self.assertTrue(person.active)
        self.assertTrue(patient.active)
        self.assertTrue(person_contact.consent_to_contact_given)
        PatientManager.opt_out_patient(person)

        patient.refresh_from_db()
        person.refresh_from_db()
        person_contact.refresh_from_db()

        self.assertFalse(patient.active)
        self.assertFalse(person.active)
        self.assertFalse(person_contact.consent_to_contact_given)

    def test_opt_out_patient_with_exceptions(self):
        """Test opting out a patient with errors, invalid person_id."""
        non_existent_person = baker.prepare(Person, id=9999, organisation=self.org)

        result = PatientManager.opt_out_patient(non_existent_person)

        self.assertFalse(result)

    def test_opt_out_person(self):
        """Test opting out a person."""
        super().setUp()
        person = baker.make(
            Person,
            first_name="Bob",
            last_name="Williamns",
            organisation=self.org,
        )
        person_contact = baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254790360360",
        )
        self.assertTrue(person.active)
        self.assertTrue(person_contact.consent_to_contact_given)
        PatientManager.opt_out_person(person)

        person.refresh_from_db()
        person_contact.refresh_from_db()

        self.assertFalse(person.active)
        self.assertFalse(person_contact.consent_to_contact_given)

    def test_opt_out_person_to_with_exceptions(self):
        """Test opting out a person with errors,invalid person_id."""
        super().setUp()
        self.person = Person.objects.first()
        with self.assertRaises(
            RuntimeError, msg="An error occurred while opting out the person:"
        ):
            PatientManager.opt_out_person(person="999-000")
        self.assertTrue(self.person.active)

    def test_check_person_exists(self):
        """Test checking if a patient exists."""
        super().setUp()
        person = baker.make(
            Person,
            first_name="Bob",
            last_name="Williamns",
            organisation=self.org,
        )
        person_contact = baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254790360360",
        )
        self.assertTrue(person.active)
        person_registered = PatientManager.check_person_exists(
            person_contact.contact, self.ussd_code.ussd_code
        )
        self.assertEqual(person_registered, person)

    def test_check_person_exists_with_exception(self):
        """Test checking if a person exists with exception."""
        super().setUp()
        person = baker.make(
            Person,
            first_name="Bob",
            last_name="Williamns",
            organisation=self.org,
        )
        person_contact = baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254790360360",
        )
        self.assertTrue(person.active)
        with self.assertRaises(
            RuntimeError,
            msg="Error fetching person: USSDCode matching query does not exist.",
        ):
            PatientManager.check_person_exists(person_contact.contact, "*100#")

    def test_check_patient_exists(self):
        """Test checking if a patient exists."""
        super().setUp()
        person = baker.make(
            Person,
            first_name="Bob",
            last_name="Williamns",
            organisation=self.org,
        )
        person_contact = baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254790360360",
            organisation=self.org,
        )
        patient = baker.make(Patient, person=person, organisation=self.org)
        self.assertTrue(patient.active)
        patient_registered = PatientManager.check_patient_exists(
            person_contact.contact, self.ussd_code.ussd_code
        )
        self.assertEqual(patient_registered, patient)

    def test_check_patient_exists_with_exception(self):
        """Test checking if a patient exists with exception."""
        super().setUp()
        person = baker.make(
            Person,
            first_name="Bob",
            last_name="Williamns",
            organisation=self.org,
        )
        person_contact = baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254790360360",
            organisation=self.org,
        )
        patient = baker.make(Patient, organisation=self.org)
        self.assertTrue(patient.active)
        with self.assertRaises(
            RuntimeError,
            msg="Error fetching patient: USSDCode matching query does not exist.",
        ):
            PatientManager.check_patient_exists(person_contact.contact, "*100#")


class TestUSSDSegments(LoggedInMixin):
    """Test for ussd segments."""

    def setUp(self):
        """Setup test environment."""
        super().setUp()
        self.org = self.global_organisation

        self.segment1 = baker.make(
            Segment,
            name="Segment 1",
            organisation=self.org,
            created_by=self.user.id,
            status="ACTIVE",
            ussd_enabled=True,
        )
        self.segment2 = baker.make(
            Segment,
            name="Segment 2",
            organisation=self.org,
            created_by=self.user.id,
            status="RETIRED",
            ussd_enabled=True,
        )
        self.segment3 = baker.make(
            Segment,
            name="Segment 3",
            organisation=self.org,
            created_by=self.user.id,
            status="ACTIVE",
            ussd_enabled=True,
        )
        self.segment4 = baker.make(
            Segment,
            name="Segment 4",
            organisation=self.org,
            created_by=self.user.id,
            status="DRAFT",
            ussd_enabled=True,
        )

        self.person = Person.objects.first()

    def test_get_organisation_segments(self):
        """Return active organisation segments where the person is not a member."""
        baker.make(
            SegmentMember,
            person=self.person,
            segment=self.segment1,
            organisation=self.org,
            created_by=self.user.id,
        )
        baker.make(
            SegmentMember,
            person=self.person,
            segment=self.segment4,
            organisation=self.org,
            created_by=self.user.id,
        )
        all_segments = Segment.objects.all()
        self.assertEqual(len(all_segments), 4)
        # Call the function to test with the Person instance
        segments = SegmentManager.get_available_segments_for_person(self.person)

        # Assert the correct segments are returned
        self.assertEqual(len(segments), 1)
        self.assertEquals(segments[0], "Segment 3")
        self.assertNotIn(self.segment1.name, segments)
        self.assertNotIn(self.segment2.name, segments)
        self.assertNotIn(self.segment4.name, segments)

    def test_add_person_to_segment_success(self):
        """Test adding a person to a segment."""
        region = baker.make(
            OperatingRegion,
            name="Nairobi",
            organisation=self.org,
            unit_type="COUNTY",
        )
        self.person.associated_region = region
        self.person.save()

        result = SegmentManager.add_person_to_segment(
            self.person,
            self.segment1.name,
        )

        self.assertTrue(result)
        self.assertEqual(SegmentMember.objects.count(), 1)
        segment_member = SegmentMember.objects.first()
        self.assertEqual(segment_member.person, self.person)
        self.assertEqual(segment_member.segment, self.segment1)
        assert self.person.associated_region == region

    def test_add_person_to_segment_with_exceptions(self):
        """Test add person to segment with errors,invalid segment_id."""
        with self.assertRaises(RuntimeError, msg="Error adding person to segment:"):
            SegmentManager.add_person_to_segment(
                person=self.person,
                segment_name="",
            )
        self.assertEqual(SegmentMember.objects.count(), 0)
