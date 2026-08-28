"""Test for common models in the application."""
import datetime
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import activate
from model_bakery import baker
from sil_erp_client.client import ERP, ApiConnection
from sil_wrapper_utils.exceptions import ItemNotFound

from sil_advantage.common.constants import (
    ONBOARDING_SESSION_LEVEL_STATUSES,
    ORGANISATION_ONBOARDING_PREFERENCES,
    ORGANIZATION_ONBOARDING_STATUSES,
)
from sil_advantage.common.models import (
    Organisation,
    OrganisationOnboarding,
    OrganisationTransitionLog,
    OrgUnit,
    Person,
    PersonContact,
    PersonID,
    UserProfile,
)
from sil_advantage.common.models.common_models import Practitioner
from sil_advantage.patients.models import Patient
from sil_advantage.visits.models import Queue
from tests.common.test_common_views import (
    LoggedInMixin,
    TestResponse,
    global_organisation,
)
from tests.common.utility import PicklableMagicMock

MOCK_ROOT = "sil_advantage.common.models.common_models."
MOCK_ORG_ROOT = "sil_advantage.common.models.organisation_models."


class OrganisationModelTest(TestCase):
    """Test for the OrganisationModel."""

    def test_unicode(self):
        """Test for the unicode."""
        org_name = "SIL"
        org = baker.make(
            Organisation,
            organisation_name=org_name,
        )
        assert str(org) == org_name
        assert org.short_name == org_name

    @override_settings(
        SYNC_WITH_ERP=True,
        ERP_API_CONFIG={
            "api_host": "uat-invoice-discounting-api.healthcloud.co.ke/api",
            "api_scheme": "https",
            "oauth_client_id": "1oauth-client-id",
            "oauth_client_secret": "2oauth-client-secret",
            "user_email": "erp.testing@slade360.co.ke",
            "user_password": "avErYsecurepa33w0rd",
            "token_url": "https://authserver.multitenant.slade360.co.ke/oauth2/token/",
        },
    )
    @patch.object(ERP, "currencies", create=True)
    @patch.object(ERP, "customers", create=True)
    @patch.object(ERP, "workstations", create=True)
    @patch.object(ERP, "organisations", create=True)
    @patch.object(
        ApiConnection, "credentials", create=True, new_callable=PicklableMagicMock
    )
    @patch.object(ApiConnection, "_get_token")
    def test_sync_with_erp_on_save(
        self,
        mock_erp_auth,
        mock_credz,
        mock_erp_orgs,
        mock_erp_workstations,
        mock_erp_customers,
        mock_erp_currencies,
    ):
        """Test Organisation sync with ERP."""

        def get_erp_org(filter):
            if filter["slade_code"] == 1:
                return {"id": "1107dee0-fa04-4187-a8e8-a4489141d13f"}
            else:
                raise ItemNotFound("Org not found")

        mock_erp_orgs.get_with.side_effect = get_erp_org
        mock_credz.__getitem__.return_value = "435wersgfs45t"
        mock_erp_orgs.setup_organisation.return_value = {
            "id": "8f114393-bc23-4920-85e5-95b12150846c",
        }
        mock_erp_customers.get_with().__getitem__.return_value = None
        mock_erp_currencies.list.return_value = {
            "results": [
                {
                    "id": "fcbe2d8e-73fc-4f01-8b53-e52c132c58b0",
                }
            ]
        }
        mock_erp_workstations.list.return_value = {
            "results": [
                {
                    "id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
                    "org_unit": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
                    "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
                    "workstation_type": "pharmacy_dispensing",
                },
                {
                    "id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
                    "org_unit": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
                    "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
                    "workstation_type": "broken",
                },
            ]
        }

        def mocked_erp_init(
            self,
            api_host,
            api_scheme,
            oauth_client_id,
            oauth_client_secret,
            user_email,
            user_password,
            token_url,
            scopes=None,
            auth_retries=3,
            auth_retry_delay=1,
            timeout_retries=6,
            timeout_retry_delay=10,
        ):
            self.conn = ApiConnection(
                host=api_host,
                oauth_id=oauth_client_id,
                oauth_secret=oauth_client_secret,
                user_email=user_email,
                user_password=user_password,
                scheme=api_scheme,
                token_url=token_url,
                scopes=scopes,
                auth_retries=auth_retries,
                auth_retry_delay=auth_retry_delay,
                timeout_retries=timeout_retries,
                timeout_retry_delay=timeout_retry_delay,
            )

        # Org doesn't exist on ERP
        assert Queue.objects.count() == 0
        with patch.object(ERP, "__init__", mocked_erp_init):
            # Create organisation, not on ERP
            org = baker.make(
                Organisation,
                slade_code=12389,
                organisation_name="Oregon Health Demo",
                email_address="oregon@slade360.co.ke",
                phone_number="+254712345678",
                description="",
                postal_address="15-10100",
                physical_address="Kimathi Way",
                default_country="KEN",
                financial_year_start_date=datetime.date(2022, 1, 1),
            )
            assert mock_erp_orgs.get_with.call_count == 2
            mock_erp_orgs.setup_organisation.assert_called_once_with(
                {
                    "slade_code": 12389,
                    "organisation_name": "Oregon Health Demo",
                    "email_address": "oregon@slade360.co.ke",
                    "phone_number": "+254712345678",
                    "description": "",
                    "postal_address": "15-10100",
                    "physical_address": "Kimathi Way",
                    "default_country": "KEN",
                    "financial_year_start_date": "2022-01-01",
                    "client_types": [
                        {"name": "Healthcare Provider", "code": "PROVIDER"}
                    ],
                }
            )
            self.assertEqual("8f114393-bc23-4920-85e5-95b12150846c", str(org.id))
            assert Queue.objects.count() == 1

            # Test idempotency
            org.create_queues_for_workstations()
            assert Queue.objects.count() == 1

            # Create organisation, exists on ERP
            mock_erp_orgs.reset_mock(return_value=True, side_effect=True)
            mock_erp_orgs.get_with.side_effect = None
            mock_erp_orgs.get_with.return_value = {
                "id": "e9efafd2-c17d-4c62-ad07-a04d45cbe786",
            }
            org2 = baker.make(
                Organisation,
                slade_code=42,
                organisation_name="Demo Hospital",
                email_address="demo@slade360.co.ke",
                phone_number="+254712345678",
                description="",
                postal_address="150-10100",
                physical_address="Kimathi Way",
                default_country="KEN",
                financial_year_start_date=datetime.date(2022, 1, 1),
            )
            mock_erp_orgs.get_with.assert_called_once_with({"slade_code": 42})
            mock_erp_orgs.setup_organisation.assert_not_called()
            self.assertEqual("e9efafd2-c17d-4c62-ad07-a04d45cbe786", str(org2.id))
            assert Queue.objects.count() == 2

            # Create the org as an ERP customer
            mock_erp_customers.reset_mock(return_value=True, side_effect=True)
            mock_erp_customers.get_with.side_effect = ItemNotFound("404")
            mock_erp_customers.create.return_value = {
                "id": "1da73f82-90d2-437e-aeef-600328b16d7b"
            }
            org.create_customer_on_erp()
            assert str(org.customer_id) == "1da73f82-90d2-437e-aeef-600328b16d7b"

    @override_settings(
        SYNC_WITH_CLINICAL_SERVICE=True,
        CLINICAL_SERVICE_URL="https://clinical-multitenant-uat.savannahghi.org",
    )
    @patch.object(ERP, "conn", create=True)
    @patch.object(ERP, "__init__")  # 💀
    @patch.object(ERP, "org_units", create=True)
    @patch(MOCK_ORG_ROOT + "requests.post")
    @patch.object(
        ApiConnection, "credentials", create=True, new_callable=PicklableMagicMock
    )
    @patch.object(ApiConnection, "_get_token")
    def test_sync_with_clinical_server(
        self,
        mock_get_token,
        mock_credz,
        mock_requests,
        mock_branches,
        mock_init,
        mock_conn,
    ):
        """Test creating a tenant on the clinical server."""
        mock_init.return_value = None
        mock_credz.__getitem__.return_value = "435wersgfs45t"
        mock_requests.return_value = TestResponse(
            {"id": "083bd496-f9ab-414a-b9a1-83f0491fe0d1"}
        )
        mock_branches.list.return_value = {
            "results": [
                {
                    "id": "4b884079-803f-42ed-8ac8-fd04c172ddfc",
                    "name": "Meru",
                    "phone_number": "+254790360360",
                    "orgunit_type": "branch",
                },
            ]
        }
        org = baker.make(
            Organisation,
            slade_code=12389,
            organisation_name="Oregon Health Demo",
            email_address="oregon@slade360.co.ke",
            phone_number="+254712345678",
            description="",
            postal_address="15-10100",
            physical_address="Kimathi Way",
            default_country="KEN",
            financial_year_start_date=datetime.date(2022, 1, 1),
        )
        assert str(org.tenant_id) == "083bd496-f9ab-414a-b9a1-83f0491fe0d1"

        org.tenant_id = None
        org.create_tenant_on_clinical_server()
        org.create_facilities_on_clinical_server()
        org.refresh_from_db()
        assert str(org.tenant_id) == "083bd496-f9ab-414a-b9a1-83f0491fe0d1"
        assert OrgUnit.objects.count() == 1


class OrganisationTransitionLogModelTest(LoggedInMixin):
    """Test for the OrganisationTransitionLogModel."""

    def test_unicode(self):
        """Test for the unicode."""
        take_note = "note is good"
        note_name = baker.make(
            OrganisationTransitionLog,
            note=take_note,
            created_by="1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
        )
        assert str(note_name) == take_note


class PersonTest(TestCase):
    """Test for the person model."""

    def test_unicode(self):
        """Test for the unicode."""
        first_name = "Sheldon"
        last_name = "Cooper"
        person = baker.make(
            Person,
            first_name=first_name,
            last_name=last_name,
        )
        assert str(person) == "Sheldon Cooper"

    def test_delete(self):
        """Test for deleting."""
        organisation = baker.make(Organisation)
        baker.make(Person, _quantity=5, organisation=organisation)
        person = baker.make(Person, organisation=organisation)
        person.delete()
        assert Person.objects.count() == 5

    def test_date_of_birth_not_a_future_date(self):
        """Test to ensure dob is not in the future."""
        dob = timezone.now().date() + datetime.timedelta(days=1)

        with pytest.raises(ValidationError):
            baker.make(Person, date_of_birth=dob)

    def test_date_of_birth_not_older_than_150_years(self):
        """Test to ensure that dob is no more than 150."""
        days = 365 * 151
        dob = timezone.now().date() - datetime.timedelta(days=days)

        with pytest.raises(ValidationError):
            baker.make(Person, date_of_birth=dob)

    def test_date_of_birth_success(self):
        """Test to ensure that dob is successful."""
        days = 365 * 20
        dob = timezone.now().date() - datetime.timedelta(days=days)
        person = baker.make(Person, date_of_birth=dob)
        assert person

    @patch(MOCK_ROOT + "timezone")
    def test_get_age(self, mock_timezone):
        """Test getting a person's age."""
        leo = parse_datetime("2022-11-16T21:48:13.899716+03:00")
        mock_timezone.now.return_value = leo

        kitambo = leo.replace(year=leo.year - 19)
        barobaro = baker.make(Person, date_of_birth=kitambo)
        assert barobaro.age == {
            "years": 19,
            "months": 0,
            "weeks": 0,
            "days": 0,
        }

        youngin = baker.make(Person, date_of_birth=leo - timedelta(days=605))
        assert youngin.age == {
            "years": 1,
            "months": 7,
            "weeks": 3,
            "days": 5,
        }

    def test_phone_number_validation(self):
        """Test for validating the phone number."""
        bad_contact = "0700000000000000"
        org = baker.make(Organisation)
        person = baker.make(Person, organisation=org)
        activate("fr")

        with self.assertRaises(ValidationError) as c:
            baker.make(
                PersonContact,
                contact=bad_contact,
                contact_type="phone_number",
                person=person,
                organisation=org,
            )

        assert "Saisissez un numéro de téléphone valide" in str(
            c.exception.args[0]
        )  # test french validation error

        activate("en")

        with self.assertRaises(ValidationError) as c:
            baker.make(
                PersonContact,
                contact=bad_contact,
                contact_type="phone_number",
                person=person,
                organisation=org,
            )
        assert "Enter a valid phone number" in str(
            c.exception.args[0]
        )  # test english translation

    def test_phone_number_property(self):
        """Test for checking phone number_property."""
        contact = "+254707038109"
        org = baker.make(Organisation)
        person = baker.make(Person, organisation=org)
        person2 = baker.make(Person, organisation=org)
        phone_contact = baker.make(
            PersonContact,
            contact=contact,
            contact_type="phone_number",
            person=person,
            organisation=org,
        )
        assert person.phone_number == contact
        assert person2.phone_number is None
        assert phone_contact.is_phone_number is True

    def test_global_health_id_property(self):
        """Test for checking phone number_property."""
        org = baker.make(Organisation)
        person = baker.make(Person, organisation=org)

        person2 = baker.make(Person, organisation=org)
        patient = baker.make(Patient, organisation=org, person=person2)

        patient.global_health_id = "1234432112344321"
        patient.save()

        assert person.global_health_id is None
        assert person2.global_health_id == "1234432112344321"

    def test_phone_number_property_with_primary_contact_set(self):
        """Test for checking phone number_property."""
        contact = "+254707038109"
        contact_two = "+254707258105"
        org = baker.make(Organisation)
        person = baker.make(Person, organisation=org)
        person2 = baker.make(Person, organisation=org)
        phone_contact = baker.make(
            PersonContact,
            contact=contact,
            contact_type="phone_number",
            person=person,
            organisation=org,
            is_primary_contact=True,
        )
        phone_contact_two = baker.make(
            PersonContact,
            contact=contact_two,
            contact_type="phone_number",
            person=person,
            organisation=org,
            is_primary_contact=False,
        )

        assert person.phone_number == contact
        assert person2.phone_number is None
        assert phone_contact.is_phone_number is True
        assert phone_contact_two.is_phone_number is True

    def test_email_property(self):
        """Test for the email property."""
        contact = "norman@gmail.com"
        org = baker.make(Organisation)
        person = baker.make(Person, organisation=org)
        person2 = baker.make(Person, organisation=org)
        baker.make(
            PersonContact,
            contact=contact,
            contact_type="email",
            person=person,
            organisation=org,
        )
        assert person.email == contact
        assert person2.email is None


class PersonIDTest(TestCase):
    """Test class for model PersonID."""

    def test_unicode(self):
        """Test for unicode."""
        value = "309485948"
        org = baker.make(Organisation)
        person = baker.make(Person, organisation=org)
        id_type = "nationalID"
        user_id = baker.make(
            PersonID,
            id_value=value,
            id_document_type=id_type,
            organisation=org,
            person=person,
        )
        expected = "{} {}".format(id_type, value)
        assert str(user_id) == expected

    def test_consistent_org_success(self):
        """Test for consistent_org_success."""
        user = get_user_model().objects.create_user(
            guid=uuid.uuid4(), email="mail@mail.com", password="pass123"
        )
        organisation = baker.make(Organisation)
        person = baker.make(Person, organisation=organisation)
        id_type = "nationalID"
        p = PersonID(
            id_document_type=id_type,
            person=person,
            id_value="vall",
            organisation=organisation,
            created_by=user.pk,
            updated_by=user.pk,
        )
        p.save()

        record = PersonID.objects.count()
        assert record == 1

    def test_kra_document_type__success(self):
        """Test for consistent_org_success."""
        user = get_user_model().objects.create_user(
            guid=uuid.uuid4(), email="mail@mail.com", password="pass123"
        )
        organisation = baker.make(Organisation)
        person = baker.make(Person, organisation=organisation)
        id_type = "kraPIN"
        p = PersonID(
            id_document_type=id_type,
            person=person,
            id_value="vall",
            organisation=organisation,
            created_by=user.pk,
            updated_by=user.pk,
        )
        p.save()

        record = PersonID.objects.count()
        assert record == 1
        assert p.id_document_type == "kraPIN"

    def test_consistent_org_fail(self):
        """Test for consistent org fail."""
        organisation = baker.make(Organisation)
        organisation1 = baker.make(Organisation)
        person = baker.make(Person, organisation=organisation)
        id_type = "NationalID"
        error_msg = (
            "The organisation provided is not consistent with that of "
            "organisation fields in related resources"
        )
        with pytest.raises(ValidationError) as e:
            p = PersonID(
                id_document_type=id_type,
                person=person,
                id_value="vall",
                organisation=organisation1,
            )
            p.save()

        assert error_msg in e.value.messages


class PersonContactTest(TestCase):
    """Test class for PersonContact model."""

    def test_unicode(self):
        """Test for the unicode."""
        first_name = "John"
        last_name = "Doe"
        contact_no = "+254729372839"
        contact_type = "phone_number"
        org = baker.make(Organisation)
        user = baker.make(
            Person,
            first_name=first_name,
            last_name=last_name,
            organisation=org,
        )

        contact = baker.make(
            PersonContact,
            person=user,
            contact=contact_no,
            contact_type=contact_type,
            organisation=org,
        )
        expected = " ".join([first_name, last_name, contact_no])
        assert str(contact) == expected

    def test_phone_number_is_digits(self):
        """Test to ensure that the phone number is made of digits."""
        user = get_user_model().objects.create_user(
            guid=uuid.uuid4(), email="mail@mail.com", password="pass123"
        )
        phone_number = "+254725332343"
        contact_type = "phone_number"
        organisation = baker.make(Organisation)
        first_name = "Denis"
        last_name = "Karanja"
        user = baker.make(
            Person,
            first_name=first_name,
            last_name=last_name,
            organisation=organisation,
            created_by=user.pk,
            updated_by=user.pk,
        )

        contact = PersonContact(
            contact=phone_number,
            contact_type=contact_type,
            organisation=organisation,
            person=user,
            created_by=user.pk,
            updated_by=user.pk,
        )

        contact.save()

    def test_valid_email_address(self):
        """Test for valid email."""
        user = get_user_model().objects.create_user(
            guid=uuid.uuid4(), email="mail@mail.com", password="pass123"
        )
        email_address = "dee.caranja@gmail.com"
        contact_type = "email"
        org = baker.make(Organisation)
        first_name = ("Denis",)
        last_name = "Karanja"
        user = baker.make(
            Person,
            first_name=first_name,
            last_name=last_name,
            organisation=org,
            created_by=user.pk,
            updated_by=user.pk,
        )

        contact = PersonContact(
            contact=email_address,
            contact_type=contact_type,
            organisation=org,
            person=user,
            created_by=user.pk,
            updated_by=user.pk,
        )

        contact.save()

    def test_invalid_email_address(self):
        """Test for invalid email."""
        email_address = "d.karanjai"
        contact_type = "email"
        org = baker.make(Organisation)
        first_name = ("Denis",)
        last_name = "Karanja"

        with pytest.raises(ValidationError) as e:
            user = baker.make(
                Person,
                first_name=first_name,
                last_name=last_name,
                organisation=org,
            )

            contact = PersonContact(
                contact=email_address,
                contact_type=contact_type,
                organisation_id=org.pk,
                person=user,
            )

            contact.save()
            error_msg = {"contact": "Enter a valid email address."}
            assert error_msg in e.exception.messages

    def test_validate_phone_number_with_null_contact(self):
        """Test validate_phone_number_is_valid with null contact."""
        user = get_user_model().objects.create_user(
            guid=uuid.uuid4(), email="mail@mail.com", password="pass123"
        )
        contact_type = "phone_number"
        organisation = baker.make(Organisation)
        first_name = "Doe"
        last_name = "John"
        user = baker.make(
            Person,
            first_name=first_name,
            last_name=last_name,
            organisation=organisation,
            created_by=user.pk,
            updated_by=user.pk,
        )

        contact = PersonContact(
            contact=None,
            contact_type=contact_type,
            organisation=organisation,
            person=user,
            created_by=user.pk,
            updated_by=user.pk,
        )

        contact.save()

    def test_validate_phone_number_with_empty_contact(self):
        """Test validate_phone_number_is_valid with empty contact."""
        user = get_user_model().objects.create_user(
            guid=uuid.uuid4(), email="mail@mail.com", password="pass123"
        )
        contact_type = "phone_number"
        organisation = baker.make(Organisation)
        first_name = "Ambros"
        last_name = "Karanja"
        user = baker.make(
            Person,
            first_name=first_name,
            last_name=last_name,
            organisation=organisation,
            created_by=user.pk,
            updated_by=user.pk,
        )

        contact = PersonContact(
            contact="",
            contact_type=contact_type,
            organisation=organisation,
            person=user,
            created_by=user.pk,
            updated_by=user.pk,
        )

        contact.save()


class AuditAbstractBaseModelTest(TestCase):
    """Test for AuditAbstract."""

    def setUp(self):
        """Onset of testcase."""
        self.user_1 = baker.make(settings.AUTH_USER_MODEL)
        self.user_2 = baker.make(settings.AUTH_USER_MODEL)

    def test_owner(self):
        """Test for test owner."""
        org = baker.make(Organisation, organisation_name="Savannah Informatics")
        fake = baker.make(
            Person,
            created_by=self.user_1.pk,
            updated_by=self.user_1.pk,
            organisation=org,
        )
        fake.save()

        assert fake.organisation.slade_code == fake.owner


class UserProfileTest(TestCase):
    """Test for UserProfile."""

    def test_unicode(self):
        """Test for unicode."""
        self.organisation = global_organisation()
        self.user = get_user_model().objects.create_user(
            guid=uuid.uuid4(), email="mail@mail.com", password="pass123"
        )
        self.person = baker.make(Person)
        self.user_profile = baker.make(
            UserProfile,
            user=self.user,
            person=self.person,
            organisation=self.organisation,
        )

        expected = "{} : {}".format(self.user, self.organisation)
        assert str(self.user_profile) == expected

    def test_object_update_time_is_higher_or_equal_to_when_it_was_created(self):
        """Test that created and updated fields are correctly set."""
        self.organisation = global_organisation()
        user_profile = baker.make(UserProfile, organisation=self.organisation)

        self.assertIsNotNone(user_profile.created)
        self.assertIsNotNone(user_profile.updated)
        self.assertTrue(user_profile.updated >= user_profile.created)

    def test_preserve_created_and_created_by(self):
        """Test preserve_created_and_created_by method."""
        user_profile = baker.make(UserProfile, organisation=global_organisation())

        user_profile.created = timezone.now() - timezone.timedelta(days=1)
        user_profile.created_by = uuid.uuid4()
        user_profile.save()

        user_profile.refresh_from_db()

        # Fetch the instance again to check if values are preserved
        updated_user_profile = UserProfile.objects.get(pk=user_profile.pk)

        # Check if created and created_by are not affected
        self.assertEqual(updated_user_profile.created, user_profile.created)
        self.assertEqual(updated_user_profile.created_by, user_profile.created_by)


class PractitionerTest(TestCase):
    """Tests for Practitioner."""

    def setUp(self):
        """Setup test environment."""
        self.organisation = global_organisation()
        self.person = baker.make(
            Person,
            title="Dr",
            first_name="John",
            other_names="Njuguna",
            last_name="Doe",
        )

    def test_unicode(self):
        """Test for unicode."""
        practitioner = baker.make(
            Practitioner,
            person=self.person,
            qualification="RADIOLOGY",
        )
        expected = "{} {}".format(
            practitioner.person.title,
            practitioner.person.get_full_name(),
        )
        assert str(practitioner) == expected


class OrganisationOnboardingTest(TestCase):
    """Tests for Organisation Verification."""

    def setUp(self):
        """Test setup."""
        self.organisation = global_organisation()

    def test_creation_of_status(self):
        """Test creation of Org verification status."""
        onboarding = OrganisationOnboarding.objects.get(organisation=self.organisation)
        assert onboarding is not None
        assert (
            onboarding.verification_status == ORGANIZATION_ONBOARDING_STATUSES.PENDING
        )

    def test_creation_of_provider_session_level(self):
        """Verify provider session level is set."""
        provider_onboarding = OrganisationOnboarding.objects.get(
            organisation=self.organisation
        )

        assert provider_onboarding is not None

        self.assertEqual(
            provider_onboarding.onboarding_session_level,
            ONBOARDING_SESSION_LEVEL_STATUSES.INTERESTS,
        )
        preferences = provider_onboarding.preferences
        assert len(preferences["questions"]) == len(ORGANISATION_ONBOARDING_PREFERENCES)
