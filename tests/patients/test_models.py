"""Test for the patients models."""
import re
from datetime import date
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from model_bakery import baker
from sil_erp_client.client import ERP, ApiConnection

from sil_advantage.common.api_clients.clinical import ClinicalServiceClient
from sil_advantage.common.api_clients.erp import fetch_from_erp_cache
from sil_advantage.common.api_clients.health_crm import HealthCRMClient
from sil_advantage.common.models import (
    Organisation,
    OrgUnit,
    Person,
    PersonContact,
    PersonID,
)
from sil_advantage.patients.models import (
    SYNC_STATUS,
    Patient,
    PatientCover,
    PatientDocument,
)
from sil_advantage.settings.models import OrganisationSetting
from tests.common.test_common_views import LoggedInMixin
from tests.common.utility import PicklableMagicMock

MOCK_ROOT = "sil_advantage.common.models.common_models."


class PatientTest(LoggedInMixin):
    """Test for Person model."""

    def setUp(self):
        """Set up the test environment."""
        super().setUp()
        org = self.global_organisation
        org.tenant_id = uuid4()
        org.save()
        baker.make(
            OrgUnit,
            organisation=org,
            erp_id="f249c5e2-d4b9-4a24-8ce2-83451aeb837e",
        )

    def test_save(self):
        """Test save method for the person's details."""
        org = baker.make(Organisation)
        person = baker.make(
            Person,
            first_name="John",
            last_name="Doe",
            deceased=False,
            organisation=org,
        )
        user = uuid4()
        data = {
            "person": person,
            "organisation": org,
            "created_by": user,
            "updated_by": user,
        }
        patient = Patient.objects.create(**data)
        self.assertEqual(1, Patient.objects.count())
        person = baker.make(Person, organisation=org, date_of_birth=None)
        assert patient.person.age is None
        assert patient.source == "ADVANTAGE_USER_REGISTRATION"

    def test_patient_id(self):
        """Test patient ID."""
        org = baker.make(Organisation)
        person = baker.make(Person, organisation=org)
        patient = baker.make(Patient, person=person, organisation=org)
        assert patient.patient_id == "1"

        person2 = baker.make(Person, organisation=org)
        patient2 = baker.make(Patient, person=person2, organisation=org)
        assert patient2.patient_id == "2"

        # confirm that the sequences start afresh across orgs
        org2 = baker.make(Organisation)
        person3 = baker.make(Person, organisation=org2)
        patient3 = baker.make(Patient, person=person3, organisation=org2)
        assert patient3.patient_id == "1"
        patient2.refresh_from_db()
        patient2.save()
        assert patient2.patient_id == "2"

    def test_patient_id_custom_formatting(self):
        """Test patient ID with custom formatting."""
        org = baker.make(Organisation)
        OrganisationSetting.set_org_setting(
            org,
            "patients:patient_id_format",
            "MIRAZI/{file_number:04d}/{created:%y}",
        )
        person = baker.make(Person, organisation=org)
        patient = baker.make(Patient, person=person, organisation=org)
        expected_year = patient.created.strftime("%y")
        assert patient.patient_id == f"MIRAZI/0001/{expected_year}"

    def test_unicode(self):
        """Testing the __str__() method."""
        first_name = "Sheldon"
        last_name = "Cooper"
        org = baker.make(Organisation)
        person = baker.make(
            Person,
            first_name=first_name,
            last_name=last_name,
            organisation=org,
        )

        patient = baker.make(
            Patient,
            person=person,
            organisation=org,
        )
        assert str(patient) == "Patient ID: 1"

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
    @patch.object(ERP, "customers", create=True)
    @patch.object(ERP, "currencies", create=True)
    @patch.object(ERP, "setup")
    @patch.object(
        ApiConnection, "credentials", create=True, new_callable=PicklableMagicMock
    )
    @patch.object(ApiConnection, "_get_token")
    def test_sync_with_erp_on_save(
        self,
        mock_erp_auth,
        mock_credz,
        mock_erp_setup,
        mock_erp_currencies,
        mock_erp_customers,
    ):
        """Test patient sync with ERP."""
        mock_erp_currencies.list.return_value = {
            "results": [
                {
                    "id": "eec240d6-f3a6-4012-a842-852d02a385d2",
                    "iso_code": "KES",
                }
            ]
        }
        mock_erp_customers.create.return_value = {
            "id": "b9f17e45-cd51-4041-ae94-9b5c9f5c99c2",
        }
        mock_erp_customers.update.return_value = {
            "id": "b9f17e45-cd51-4041-ae94-9b5c9f5c99c2",
        }
        mock_credz.__getitem__.return_value = "435wersgfs45t"

        # Test Creation
        org = self.global_organisation
        person = baker.make(
            Person,
            first_name="John",
            last_name="Doe",
            deceased=False,
            organisation=org,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        data = {
            "person": person,
            "organisation": org,
            "created_by": self.user.id,
            "updated_by": self.user.id,
        }
        patient = Patient.objects.create(**data)
        patient.refresh_from_db()
        mock_erp_customers.create.assert_called_once_with(
            {
                "partner_name": "John Doe",
                "is_customer": True,
                "organisation": "ebef581c-494b-4772-9e49-0b0755c44e61",
                "customer_type": "PATIENT",
                "country": "KEN",
                "created_by": "1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
                "updated_by": "1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
                "currency": "eec240d6-f3a6-4012-a842-852d02a385d2",
            }
        )
        self.assertEqual(
            "b9f17e45-cd51-4041-ae94-9b5c9f5c99c2", str(patient.customer_id)
        )

        # Test Update
        person.first_name = "Jane"
        person.save()
        patient.save()

        mock_erp_currencies.list.assert_called_once_with(
            filters={
                "organisation": "ebef581c-494b-4772-9e49-0b0755c44e61",
                "is_default": True,
            }
        )
        mock_erp_customers.update.assert_called_once_with(
            UUID("b9f17e45-cd51-4041-ae94-9b5c9f5c99c2"),
            {
                "partner_name": "Jane Doe",
                "is_customer": True,
                "organisation": "ebef581c-494b-4772-9e49-0b0755c44e61",
                "customer_type": "PATIENT",
                "country": "KEN",
                "created_by": "1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
                "updated_by": "1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
            },
        )

        currencies = fetch_from_erp_cache(
            "currencies",
            "list",
            filters={
                "iso_code": "KES",
                "organisation": "ebef581c-494b-4772-9e49-0b0755c44e61",
            },
        )
        assert currencies == {
            "_cache_key": "bb825333ebb9ea5912942b6dc4fb3ed5",
            "results": [
                {
                    "id": "eec240d6-f3a6-4012-a842-852d02a385d2",
                    "iso_code": "KES",
                }
            ],
        }

    @override_settings(
        SYNC_WITH_HEALTH_CRM=True,
        HEALTH_CRM_API_URL="crm-api.slade360.uat.slade360edi.com",
        HEALTH_CRM_SERVICE_CODE="01",
    )
    @patch.object(HealthCRMClient.ProfilesAPI, "create")
    @patch.object(
        ApiConnection, "credentials", create=True, new_callable=PicklableMagicMock
    )
    @patch.object(ApiConnection, "_get_token")
    def test_sync_with_health_crm_on_save(
        self,
        mock_auth,
        mock_credz,
        mock_create_profile,
    ):
        """Test patient sync with Health CRM."""
        mock_credz.__getitem__.return_value = "435wersgfs45t"

        # Test Create
        person = baker.make(
            Person,
            first_name="John",
            last_name="Doe",
            gender="MALE",
            date_of_birth="2023-06-14",
            deceased=False,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254790360360",
        )
        baker.make(
            PersonID,
            person=person,
            id_document_type="nationalID",
            id_value="123455",
        )
        patient = Patient.objects.create(
            id="e7e5f7f7-16b2-4bc1-ad9a-ac78ed569cf0",
            person=person,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        mock_create_profile.assert_called_once_with(
            {
                "profile_id": "e7e5f7f7-16b2-4bc1-ad9a-ac78ed569cf0",
                "first_name": "John",
                "last_name": "Doe",
                "other_name": "",
                "gender": "MALE",
                "date_of_birth": date(2023, 6, 14),
                "slade_code": 50,
                "service_code": "01",
                "enrolment_date": timezone.now().date(),
                "identifiers": [
                    {
                        "identifier_type": "PATIENT_NO",
                        "identifier_value": "1",
                        "verified": True,
                    },
                    {
                        "identifier_type": "NATIONAL_ID",
                        "identifier_value": "123455",
                    },
                ],
                "contacts": [
                    {
                        "contact_type": "PHONE_NUMBER",
                        "contact_value": "+254790360360",
                        "verified": False,
                        "consent_to_contact_given": True,
                    }
                ],
            }
        )
        patient.refresh_from_db()
        self.assertEqual(patient.health_crm_sync_status, dict(SYNC_STATUS)["SUCCESS"])

        # Test Update
        mock_create_profile.reset_mock()

        person.first_name = "Jane"
        person.save()
        patient.customer_id = "f1ee42e1-bf4c-4acd-9633-ba81384a1e2d"
        patient.clinical_id = "087c9c78-04d2-4df3-8b6d-ba06bbaf8fc2"
        patient.save()

        self.assertDictEqual(
            patient.health_crm_profiles_payload,
            {
                "profile_id": "e7e5f7f7-16b2-4bc1-ad9a-ac78ed569cf0",
                "first_name": "Jane",
                "last_name": "Doe",
                "other_name": "",
                "gender": "MALE",
                "date_of_birth": date(2023, 6, 14),
                "slade_code": 50,
                "service_code": "01",
                "enrolment_date": timezone.now().date(),
                "identifiers": [
                    {
                        "identifier_type": "PATIENT_NO",
                        "identifier_value": "1",
                        "verified": True,
                    },
                    {
                        "identifier_type": "NATIONAL_ID",
                        "identifier_value": "123455",
                    },
                    {
                        "identifier_type": "ERP_CUSTOMER_ID",
                        "identifier_value": "f1ee42e1-bf4c-4acd-9633-ba81384a1e2d",
                        "verified": True,
                    },
                    {
                        "identifier_type": "FHIR_PATIENT_ID",
                        "identifier_value": "087c9c78-04d2-4df3-8b6d-ba06bbaf8fc2",
                        "verified": True,
                    },
                ],
                "contacts": [
                    {
                        "contact_type": "PHONE_NUMBER",
                        "contact_value": "+254790360360",
                        "verified": False,
                        "consent_to_contact_given": True,
                    }
                ],
            },
        )

        mock_create_profile.assert_called_once()

        patient.refresh_from_db()
        self.assertEqual(patient.health_crm_sync_status, dict(SYNC_STATUS)["SUCCESS"])
        # Test deletion
        mock_create_profile.reset_mock()
        patient.delete()
        mock_create_profile.assert_not_called()

    @override_settings(
        SYNC_WITH_HEALTH_CRM=True,
        HEALTH_CRM_API_URL="crm-api.slade360.uat.slade360edi.com",
        HEALTH_CRM_SERVICE_CODE="01",
    )
    @patch.object(
        HealthCRMClient.ProfilesAPI, "create", side_effect=Exception("Simulated error")
    )
    @patch.object(
        ApiConnection, "credentials", create=True, new_callable=PicklableMagicMock
    )
    @patch.object(ApiConnection, "_get_token")
    def test_sync_with_health_crm_on_save_failure(
        self,
        mock_auth,
        mock_credz,
        mock_create_profile,
    ):
        """Test patient sync with Health CRM failure."""
        mock_credz.__getitem__.return_value = "435wersgfs45t"

        # Test Create Failure
        person = baker.make(
            Person,
            first_name="John",
            last_name="Doe",
            gender="MALE",
            date_of_birth="2023-06-14",
            deceased=False,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254790360360",
        )
        baker.make(
            PersonID,
            person=person,
            id_document_type="nationalID",
            id_value="123455",
        )
        patient = Patient.objects.create(
            id="e7e5f7f7-16b2-4bc1-ad9a-ac78ed569cf0",
            person=person,
            organisation=self.global_organisation,
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        patient.refresh_from_db()
        self.assertEqual(patient.health_crm_sync_status, dict(SYNC_STATUS)["FAILED"])

    @override_settings(
        SYNC_WITH_CLINICAL_SERVICE=True,
        HEALTH_CRM_API_URL="https://clinical-multitenant-uat.savannahghi.org",
    )
    @patch("sil_advantage.patients.models.LOGGER")
    @patch("sil_advantage.common.api_clients.clinical.Client")
    @patch("sil_advantage.common.api_clients.clinical.get_auth_server_credentials")
    def test_sync_with_clinical_service_on_save(
        self, mock_auth, mock_gql_client, mock_logger
    ):
        """Test patient sync with the clinical service."""
        org = self.global_organisation
        clinical_id = "0e268aad-e5b4-44c0-bb4a-5e0695022559"
        mock_auth.return_value = {
            "access_token": "P8HmBs8fsNIkTL7ikcntaWtyX3stY2",
        }
        gql_client = mock_gql_client.return_value
        gql_client.execute.return_value = {
            "createPatient": {
                "id": clinical_id,
                "name": "John Doe",
                "phoneNumber": ["+254790360360"],
                "gender": "male",
                "birthDate": "2023-06-01",
                "active": True,
            },
            "patchPatient": {
                "id": clinical_id,
                "name": "Jane Doe",
                "phoneNumber": ["+254790360360"],
                "gender": "female",
                "birthDate": "2023-06-01",
                "active": True,
            },
            "deletePatient": True,
        }

        # Test Create
        person = baker.make(
            Person,
            first_name="John",
            last_name="Doe",
            gender="MALE",
            date_of_birth="2023-06-14",
            deceased=False,
            organisation=org,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        contact = baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254790360360",
        )
        person_id = baker.make(
            PersonID,
            person=person,
            id_document_type="nationalID",
            id_value="123455",
        )
        patient = Patient.objects.create(
            id="e7e5f7f7-16b2-4bc1-ad9a-ac78ed569cf0",
            person=person,
            organisation=org,
            branch_id="f249c5e2-d4b9-4a24-8ce2-83451aeb837e",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        gql_client.execute.assert_called_once()
        payload = gql_client.execute.call_args[1]["variable_values"]
        self.assertEqual(
            payload,
            {
                "input": {
                    "firstName": "John",
                    "lastName": "Doe",
                    "otherNames": "",
                    "birthDate": "2023-06-14",
                    "gender": "male",
                    "identifiers": [
                        {"type": "NATIONAL_ID", "value": "123455"},
                        {"type": "HEALTH_ID", "value": ""},
                    ],
                    "contacts": [{"type": "PHONE_NUMBER", "value": "+254790360360"}],
                }
            },
        )
        patient.refresh_from_db()
        assert str(patient.clinical_id) == clinical_id

        # Test Update
        gql_client.reset_mock()

        person.first_name = "Jane"
        person.gender = "FEMALE"
        person.save()
        patient.global_health_id = "1111222233334444"
        patient.save()

        gql_client.execute.assert_called_once()
        payload = gql_client.execute.call_args[1]["variable_values"]
        self.assertEqual(
            payload,
            {
                "id": clinical_id,
                "input": {
                    "firstName": "Jane",
                    "lastName": "Doe",
                    "otherNames": "",
                    "birthDate": "2023-06-14",
                    "gender": "female",
                    "identifiers": [
                        {"type": "NATIONAL_ID", "value": "123455"},
                        {"type": "HEALTH_ID", "value": "1111222233334444"},
                    ],
                    "contacts": [{"type": "PHONE_NUMBER", "value": "+254790360360"}],
                },
            },
        )

        contact.delete()
        person_id.delete()
        patient.delete()
        person.delete()

        # Test create with unmapped identifiers
        gql_client.reset_mock()

        person = baker.make(
            Person,
            first_name="Mary",
            last_name="Jane",
            gender="MALE",
            date_of_birth="2023-06-14",
            deceased=False,
            organisation=org,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        contact = baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254790360360",
        )
        person_id = baker.make(
            PersonID,
            person=person,
            id_document_type="nationalID",
            id_value="123455",
        )
        person_id_two = baker.make(
            PersonID,
            person=person,
            id_document_type="kraPIN",
            id_value="123455",
        )
        patient = Patient.objects.create(
            id="e7e5f7f7-16b2-4bc1-ad9a-ac78ed569cf0",
            person=person,
            organisation=org,
            branch_id="f249c5e2-d4b9-4a24-8ce2-83451aeb837e",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        gql_client.execute.assert_called_once()
        mock_logger.warning.assert_called_once_with(
            f"ID Mapping with key {person_id_two.id_document_type} does not exist."
        )

        payload = gql_client.execute.call_args[1]["variable_values"]
        self.assertEqual(
            payload,
            {
                "input": {
                    "firstName": "Mary",
                    "lastName": "Jane",
                    "otherNames": "",
                    "birthDate": "2023-06-14",
                    "gender": "male",
                    "identifiers": [
                        {"type": "NATIONAL_ID", "value": "123455"},
                        {"type": "HEALTH_ID", "value": ""},
                    ],
                    "contacts": [{"type": "PHONE_NUMBER", "value": "+254790360360"}],
                }
            },
        )
        patient.refresh_from_db()
        assert str(patient.clinical_id) == clinical_id

    @override_settings(
        SYNC_WITH_CLINICAL_SERVICE=True,
        HEALTH_CRM_API_URL="https://clinical-multitenant-uat.savannahghi.org",
    )
    @patch("sil_advantage.common.api_clients.clinical.Client")
    @patch("sil_advantage.common.api_clients.clinical.get_auth_server_credentials")
    def test_sync_with_clinical_service_on_save_with_none_values(
        self, mock_auth, mock_gql_client
    ):
        """Test patient sync with the clinical service."""
        org = self.global_organisation
        clinical_id = "0e268aad-e5b4-44c0-bb4a-5e0695022559"
        mock_auth.return_value = {
            "access_token": "P8HmBs8fsNIkTL7ikcntaWtyX3stY2",
        }
        gql_client = mock_gql_client.return_value
        gql_client.execute.return_value = {
            "createPatient": {
                "id": clinical_id,
                "name": "John Doe",
                "phoneNumber": ["+254790360360"],
                "gender": "",
                "birthDate": "",
                "active": True,
            },
            "patchPatient": {
                "id": clinical_id,
                "name": "Jane Doe",
                "phoneNumber": ["+254790360360"],
                "gender": "",
                "birthDate": "",
                "active": True,
            },
            "deletePatient": True,
        }

        # Test Create
        person = baker.make(
            Person,
            first_name="John",
            last_name="Doe",
            deceased=False,
            organisation=org,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        contact = baker.make(
            PersonContact,
            person=person,
            contact_type="phone_number",
            contact="+254790360360",
        )
        person_id = baker.make(
            PersonID,
            person=person,
            id_document_type="nationalID",
            id_value="123455",
        )
        patient = Patient.objects.create(
            id="e7e5f7f7-16b2-4bc1-ad9a-ac78ed569cf0",
            person=person,
            organisation=org,
            branch_id="f249c5e2-d4b9-4a24-8ce2-83451aeb837e",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        gql_client.execute.assert_called_once()
        payload = gql_client.execute.call_args[1]["variable_values"]
        self.assertEqual(
            payload,
            {
                "input": {
                    "firstName": "John",
                    "lastName": "Doe",
                    "otherNames": "",
                    "birthDate": "1900-01-01",
                    "gender": "OTHER",
                    "identifiers": [
                        {"type": "NATIONAL_ID", "value": "123455"},
                        {"type": "HEALTH_ID", "value": ""},
                    ],
                    "contacts": [{"type": "PHONE_NUMBER", "value": "+254790360360"}],
                }
            },
        )
        patient.refresh_from_db()
        assert str(patient.clinical_id) == clinical_id

        # Test Update
        gql_client.reset_mock()

        person.first_name = "Jane"
        person.save()
        patient.global_health_id = "1111222233334444"
        patient.save()

        gql_client.execute.assert_called_once()
        payload = gql_client.execute.call_args[1]["variable_values"]
        self.assertEqual(
            payload,
            {
                "id": clinical_id,
                "input": {
                    "firstName": "Jane",
                    "lastName": "Doe",
                    "otherNames": "",
                    "birthDate": "1900-01-01",
                    "gender": "OTHER",
                    "identifiers": [
                        {"type": "NATIONAL_ID", "value": "123455"},
                        {"type": "HEALTH_ID", "value": "1111222233334444"},
                    ],
                    "contacts": [{"type": "PHONE_NUMBER", "value": "+254790360360"}],
                },
            },
        )

        contact.delete()
        person_id.delete()
        patient.delete()
        person.delete()

    @override_settings(
        SYNC_WITH_CLINICAL_SERVICE=True,
        HEALTH_CRM_API_URL="https://clinical-multitenant-uat.savannahghi.org",
    )
    @patch("sil_advantage.integrations.mixins.LOGGER")
    @patch("sil_advantage.common.api_clients.clinical.Client")
    @patch("sil_advantage.common.api_clients.clinical.get_auth_server_credentials")
    def test_unsupported_operation_on_clinical_service(
        self, mock_auth, mock_gql_client, mock_logger
    ):
        """Test unsupported operation on the clinical service."""
        mock_auth.return_value = {
            "access_token": "P8HmBs8fsNIkTL7ikcntaWtyX3stY2",
        }
        gql_client = mock_gql_client.return_value
        gql_client.execute.return_value = {
            "createPatient": {
                "id": "0e268aad-e5b4-44c0-bb4a-5e0695022559",
                "name": "John Doe",
                "phoneNumber": ["+254790360360"],
                "gender": "male",
                "birthDate": "2023-06-01",
                "active": True,
            },
        }

        patient = baker.make(
            Patient,
            organisation=self.global_organisation,
            branch_id="f249c5e2-d4b9-4a24-8ce2-83451aeb837e",
            person__gender="FEMALE",
            person__date_of_birth="2023-07-07",
        )

        patient._perform_operation_on_clinical_service("GET")
        mock_logger.warning.assert_called_once_with(
            "Mutation get_patient not implemented"
        )

        mock_logger.reset_mock()
        with patch.object(ClinicalServiceClient, "get_patient", create=True):
            patient._perform_operation_on_clinical_service("GET")
            mock_logger.warning.assert_called_once_with(
                "Unsupported operation GET",
            )

    def test_override_patient_creation_date(self):
        """Test overriding a patient's creation date.

        This is to address an issue we found at Mirazi where they
        already had patient registration dates which was messing
        up for file number sequencing.
        """
        org = self.global_organisation
        person1, person2, person3, person4 = baker.make(
            Person,
            organisation=org,
            _quantity=4,
        )
        field = Patient._meta.get_field("created")

        field.auto_now = False
        field.auto_now_add = False
        Patient.objects.create(
            person=person1,
            created="2023-01-01",
            organisation=org,
            updated_by=uuid4(),
            created_by=uuid4(),
        )

        field.auto_now = True
        field.auto_now_add = True
        Patient.objects.create(
            person=person2,
            organisation=org,
            updated_by=uuid4(),
            created_by=uuid4(),
        )

        field.auto_now = False
        field.auto_now_add = False
        Patient.objects.create(
            person=person3,
            created="2023-06-01",
            organisation=org,
            updated_by=uuid4(),
            created_by=uuid4(),
        )

        field.auto_now = True
        field.auto_now_add = True
        patient = Patient.objects.create(
            person=person4,
            organisation=org,
            updated_by=uuid4(),
            created_by=uuid4(),
        )
        assert patient.file_number == 4


class PatientDocumentTest(LoggedInMixin):
    """Test for patient document model."""

    def setUp(self):
        """Create a url for use in test."""
        self.url_list = reverse("patientdocument-list")
        super().setUp()

    def _get_file(self, filename):
        with open(f"tests/assets/{filename}", "r+b") as myfile:
            read_file = myfile.read()
            memory = SimpleUploadedFile(
                "image",
                read_file,
                content_type="image/jpeg",
            )
            return memory

    def test_save_document(self):
        """Test photo name match."""
        title = "Picture 1"
        org = self.global_organisation
        patient = baker.make(Patient, organisation=org)
        file = self._get_file("test_image.jpeg")
        payload = {
            "data": file,
            "title": "Picture 1",
            "size": 2000,
            "organisation": org,
            "patient": patient,
            "description": "Some descr",
            "content_type": "image/jpeg",
            "document_type": "OTHER",
            "visit_date": "2023-05-17",
        }
        document = baker.make(
            PatientDocument,
            **payload,
            _create_files=True,
        )
        self.assertEqual(1, PatientDocument.objects.count())
        assert str(document) == title

    def test_retrieve_document(self):
        """Test retrieve document."""
        org = self.global_organisation
        person = baker.make(
            Person,
            first_name="Sheldon",
            last_name="Cooper",
            organisation=org,
        )
        patient = baker.make(
            Patient,
            person=person,
            file_number=14,
            organisation=org,
        )
        baker.make(
            PatientDocument,
            title="Picture 1",
            organisation=org,
            patient=patient,
            _create_files=True,
        )
        baker.make(
            PatientDocument,
            title="Picture 2",
            organisation=org,
            patient=patient,
            _create_files=True,
        )

        response = self.client.get(self.url_list)
        assert response.data["count"] == 2

    def test_oversize_document(self):
        """Test validation of oversize picture document."""
        file = self._get_file("test_image_oversize.jpeg")
        org = baker.make(Organisation)
        person = baker.make(
            Person,
            organisation=org,
        )
        patient = baker.make(Patient, organisation=org, person=person)
        payload = {
            "data": file,
            "title": "Picture 1",
            "size": 2000,
            "organisation": org,
            "patient": patient,
            "description": "Some descr",
            "content_type": "image/jpeg",
            "document_type": "OTHER",
            "visit_date": "2023-05-17",
        }
        msg = (
            "Your image has a height of 4800 and width of 7680 "
            "pixels which is larger than allowable dimension of "
            "2400 pixels."
        )
        with self.assertRaises(Exception) as context:
            baker.make(
                PatientDocument,
                **payload,
            )
            self.assertTrue({"__all__": [msg]} in context.exception)

    @patch(MOCK_ROOT + "LOGGER")
    def test_catch_all_exception(self, mock_logger):
        """Test catch-all exception with missing file."""
        org = self.global_organisation
        patient = baker.make(Patient, organisation=org)
        file = self._get_file("test_image.jpeg")
        payload = {
            "data": file,
            "title": "Picture 1",
            "size": 2000,
            "organisation": org,
            "patient": patient,
            "description": "Some descr",
            "content_type": "image/jpeg",
            "document_type": "OTHER",
            "visit_date": "2023-05-17",
        }
        document = baker.make(
            PatientDocument,
            **payload,
            _create_files=True,
        )

        with pytest.raises(ValidationError):
            document.data.delete()

        mock_logger.exception.assert_called_once_with(
            "PatientDocument - The 'data' attribute has no file associated with it."
        )

    def tearDown(self) -> None:
        """Tear down test suite."""
        super().tearDown()
        cache.clear()


class PatientCoverTest(LoggedInMixin):
    """Test for PatientCover model."""

    def setUp(self):
        """Setup the test environment."""
        super().setUp()
        org = self.global_organisation
        org.save()
        person = baker.make(
            Person, first_name="Sarah", last_name="Doe", organisation=org
        )
        self.patient = baker.make(Patient, person=person, organisation=org)

    def test_validate_valid_to_greater_than_valid_from(self):
        """Test validating valid_to must be greater than valid_from."""
        org = self.global_organisation
        user = uuid4()
        invalid_data = {
            "scheme_name": "NHIF",
            "member_number": "NH132",
            "patient": self.patient,
            "scheme_id": "eaca7a4c-8d0f-4906-bccf-eacf492cfd1c",
            "payer_id": "eaca7a4c-8d0f-4906-bccf-eacf492cfd1d",
            "valid_from": "2024-03-15",
            "valid_to": "2024-03-10",
            "organisation": org,
            "created_by": user,
            "updated_by": user,
        }

        expected_error = re.escape(
            "{'__all__': ['valid_to must be greater than valid_from']}"
        )
        with pytest.raises(ValidationError, match=expected_error):
            baker.make(PatientCover, **invalid_data)

    def test_save(self):
        """Test saving patients cover."""
        org = self.global_organisation
        user = uuid4()
        data = {
            "scheme_name": "NHIF",
            "member_number": "NH132",
            "patient": self.patient,
            "scheme_id": "eaca7a4c-8d0f-4906-bccf-eacf492cfd1c",
            "payer_id": "eaca7a4c-8d0f-4906-bccf-eacf492cfd1d",
            "organisation": org,
            "created_by": user,
            "updated_by": user,
        }
        cover = PatientCover.objects.create(**data)
        self.assertEqual(1, PatientCover.objects.count())
        self.assertEqual(str(cover), "Sarah Doe - NHIF")

    def test_validate_unique_together(self):
        """Test validating scheme id and patient are unique together."""
        org = self.global_organisation
        user = uuid4()
        baker.make(
            PatientCover,
            scheme_name="NHIF",
            member_number="NH132",
            patient=self.patient,
            scheme_id="eaca7a4c-8d0f-4906-bccf-eacf492cfd1c",
            payer_id="eaca7a4c-8d0f-4906-bccf-eacf492cfd1d",
            valid_from="2024-03-15",
            valid_to="2024-03-16",
            organisation=org,
            created_by=user,
            updated_by=user,
        )
        data = {
            "scheme_name": "NHIF",
            "member_number": "NH132",
            "patient": self.patient,
            "scheme_id": "eaca7a4c-8d0f-4906-bccf-eacf492cfd1c",
            "payer_id": "eaca7a4c-8d0f-4906-bccf-eacf492cfd1d",
            "valid_from": "2024-03-15",
            "valid_to": "2024-03-16",
            "organisation": org,
            "created_by": user,
            "updated_by": user,
        }
        with self.assertRaises(ValidationError):
            PatientCover.objects.create(**data)
