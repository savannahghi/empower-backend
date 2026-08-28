"""Test for the common views."""
import uuid
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from os import path
from typing import Any
from unittest.mock import patch

import orjson
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.client import RequestFactory
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from model_bakery import baker
from model_bakery.recipe import Recipe
from rest_framework.test import APITestCase
from sil_auth_backends.utilities.utilities import extract_perm_from_module
from sil_monitoring.monitor import Monitor
from social_django.models import UserSocialAuth

from sil_advantage.common.models import (
    Consent,
    ConsentStatus,
    ConsentType,
    OperatingRegion,
    Organisation,
    OTPVerificationStatus,
    Person,
    PersonContact,
    PersonID,
    PersonOTP,
    UserProfile,
)
from sil_advantage.permissions import perms
from sil_advantage.sil_auth.models import SILUser

from .utility import patch_baker

DIR_PATH = path.join(path.dirname(path.abspath(__file__)))
MEDIA_PATH = path.join(DIR_PATH, "media")

http_origin_header = {"HTTP_ORIGIN": "http://sil_advantage.com"}


def global_organisation():
    """Create organisation for running test."""
    org_id = "ebef581c-494b-4772-9e49-0b0755c44e61"
    slade_code = 50
    organisation_name = "Demo Hospital"
    physical_address = "The Badlands"
    a_week_ago = timezone.now().date() - timedelta(days=7)
    org, _ = Organisation.objects.get_or_create(
        id=org_id,
        slade_code=slade_code,
        organisation_name=organisation_name,
        created_by="ebef581c-494b-4772-9e49-0b0755c44e61",
        updated_by="ebef581c-494b-4772-9e49-0b0755c44e61",
        defaults={
            "financial_year_start_date": a_week_ago,
            "physical_address": physical_address,
            "phone_number": "+254799999999",
        },
    )
    return org


def get_project_permissions():
    """Get all advantage permissions."""
    nested_perms = extract_perm_from_module(perms)
    permissions = []
    for perm in nested_perms:
        permissions.append(perm["name"])
        permissions.extend(perm["children"])
    return permissions


@dataclass
class TestResponse:
    """A class to help mock HTTP request responses."""

    __test__ = False

    data: dict[str, Any] | str
    status_code: int = 200

    @property
    def content(self) -> str:
        """Content of the response, as a `str`."""
        if isinstance(self.data, dict):
            return orjson.dumps(self.data).decode("utf-8")
        return self.data

    def json(self) -> dict[str, Any]:
        """Return a dictionary version of the response data."""
        return self.data


class LoggedInMixin(APITestCase):
    """Define a logged in session for use in tests."""

    maxDiff = None

    def setUp(self):
        """Create a test user for the logged in session."""
        super().setUp()
        permissions = set(get_project_permissions())
        permissions.remove(perms.CROSS_NETWORK_ADMIN[0])
        permissions.remove(perms.ORGANISATION_ADMIN[0])
        permissions.remove(perms.BRANCH_ADMIN[0])
        permissions.remove(perms.CLUSTER_ADMIN[0])
        permissions = ",".join(permissions)
        self.user = get_user_model().objects.create_superuser(
            email="mail@mail.com",
            password="pass123",
            id="1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
            guid="1d7494c0-2d13-4140-aa54-2ef7d14e48cd",
            matrix_user_id="@2bdf4e17-cb39-4626-a29d-a80040d67857:slade360edi.com",
            permissions=permissions,
        )
        self.global_person = baker.make(
            Person,
            organisation=self.global_organisation,
            first_name="John",
            last_name="Doe",
        )
        self.user_profile = baker.make(
            UserProfile,
            user=self.user,
            person=self.global_person,
            organisation=self.global_organisation,
        )
        assert self.client.login(username="mail@mail.com", password="pass123") is True

        # Fake Oauth token to test syncing with the ERP
        baker.make(
            UserSocialAuth,
            user=self.user,
            extra_data={"access_token": "OauthToken123"},
        )

        # create a second test user for multi-step approval
        self.user_2 = get_user_model().objects.create_superuser(
            email="user2@mail.com",
            password="pass123",
            guid=uuid.uuid4(),
            permissions=permissions,
        )
        self.global_person_2 = baker.make(
            Person,
            organisation=self.global_organisation,
            first_name="Jesse",
            last_name="Pinkman",
        )
        self.user_profile_2 = baker.make(
            UserProfile,
            user=self.user_2,
            person=self.global_person_2,
            organisation=self.global_organisation,
        )

        self.patch_organisation = partial(
            patch_baker, values={"organisation": self.global_organisation}
        )

        self.org_patcher = self.patch_organisation()
        self.org_patcher.start()

        self.addCleanup(self.org_patcher.stop)

        headers = self.extra_headers()
        self.client.get = partial(self.client.get, **headers)
        self.client.patch = partial(self.client.patch, **headers)
        self.client.post = partial(self.client.post, **headers)
        self.client.put = partial(self.client.put, **headers)

    def assign_permission(self, perm):
        """Assign permission to created test user."""
        perms = self.user.permissions.split(",")
        perms.extend(perm)
        self.user.permissions = ",".join(perms)
        self.user.save()

    def make_user_super_admin(self):
        """Make the test user a super admin."""
        self.assign_permission([perms.CROSS_NETWORK_ADMIN[0]])

    def make_user_org_admin(self):
        """Make the test user an organisation admin."""
        self.assign_permission([perms.ORGANISATION_ADMIN[0]])

    @cached_property
    def global_organisation(self):
        """Create test organisaion for the user."""
        return global_organisation()

    def make_recipe(self, model, **kwargs):
        """Ensure test user part of an organisation."""
        if "organisation" not in kwargs:
            kwargs["organisation"] = self.user.organisation
        return Recipe(model, **kwargs)

    def extra_headers(self):
        """Return an empty headers list."""
        return {}

    def tearDown(self) -> None:
        """Clear the cache in between tests."""
        cache.clear()
        return super().tearDown()


class HomeTestCase(TestCase):
    """Test suite for the homepage."""

    def setUp(self):
        """Create a test homepage."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.factory = RequestFactory()
        self.guid = str(uuid.uuid4())
        self.user = get_user_model().objects.create_superuser(
            email="mail@mail.com", password="pass123", guid=self.guid
        )
        self.global_person = baker.make(Person)
        org = baker.make(Organisation, id="472854fd-8fb4-48d8-91b1-7ae249f5b3f9")
        self.user_profile = baker.make(
            UserProfile,
            user=self.user,
            person=self.global_person,
            organisation=org,
        )
        assert self.client.login(username="mail@mail.com", password="pass123") is True

    @patch.object(Monitor, "timer")
    def test_home(self, mock_timer):
        """Test success for homepage request."""
        url = reverse("homepage")
        response = self.client.get(url)
        assert response.status_code == 200
        mock_timer.assert_not_called()


@override_settings(
    DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage",
    MEDIA_ROOT=MEDIA_PATH,
    DISABLE_ORG_SETUP=True,
)
class OrganisationViewTest(LoggedInMixin):
    """Test suite for an organisation."""

    def setUp(self):
        """Details for test organisation."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.url_list = reverse("organisation-list")
        self.url_upd_special = "organisation-update-organisation"
        super().setUp()

    def test_create_organisation(self):
        """Test organisation creation success."""
        data = {
            "organisation_name": "Coptic",
            "code": 59,
            "phone_number": "+254721585473",
            "default_country": "KEN",
            "slade_code": 2001,
            "email_address": "me@me.com",
            "created_by": self.user.pk,
            "updated_by": self.user.pk,
            "financial_year_start_date": "2016-11-07",
        }
        response = self.client.post(self.url_list, data)
        assert response.status_code == 201
        assert response.data["organisation_name"] == data["organisation_name"]

    def test_organisation_update_view(self):
        """It should update an organisations client types."""
        org = baker.make(Organisation, description=None)
        url = reverse(self.url_upd_special, kwargs={"pk": org.id})
        self.make_user_super_admin()
        response = self.client.patch(url, {"description": "Heyo!"})
        assert response.status_code == 200

        org.refresh_from_db()
        assert org.description == "Heyo!"

    def test_get_on_detail_special_endpoint(self):
        """Test that a get returns the details of the object."""
        org = baker.make(Organisation)
        url = reverse(self.url_upd_special, kwargs={"pk": org.id})
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["id"] == str(org.id)

    def test_organisation_count_greater_than_two(self):
        """Test adding an organisation."""
        data = {
            "organisation_name": "Coptic National Hospital Kenya",
            "created_by": self.user.pk,
            "updated_by": self.user.pk,
            "slade_code": 2001,
            "phone_number": "+254721585473",
            "default_country": "KEN",
            "email_address": "me@me.com",
            "financial_year_start_date": "2016-11-07",
        }

        response = self.client.post(self.url_list, data)

        assert response.status_code == 201
        assert response.data["organisation_name"] == data["organisation_name"]

    def test_organisation_count_less_than_two(self):
        """Test organisationcount is less than two."""
        data = {
            "organisation_name": "Coptic",
            "created_by": self.user.pk,
            "updated_by": self.user.pk,
            "phone_number": "+254721585473",
            "slade_code": 2001,
            "default_country": "KEN",
            "email_address": "me@me.com",
            "financial_year_start_date": "2016-11-07",
        }

        response = self.client.post(self.url_list, data)

        assert response.status_code == 201
        assert response.data["organisation_name"] == data["organisation_name"]

    def test_retrieve_organisation(self):
        """Test creation of organisations."""
        baker.make(Organisation, organisation_name="Sil Devs")
        baker.make(Organisation, organisation_name="Coptic")

        response = self.client.get(self.url_list)
        assert response.data["count"] == 3
        organisation_names = [a["organisation_name"] for a in response.data["results"]]
        assert "Sil Devs" in organisation_names
        assert "Coptic" in organisation_names

    def test_patch_organisation(self):
        """Test for change organisation details."""
        org = baker.make(Organisation, organisation_name="Sil Devs")
        update_org_dict = {
            "organisation_name": "Coptic",
        }
        url = reverse("organisation-detail", kwargs={"pk": org.pk})
        response = self.client.patch(url, update_org_dict)

        assert response.status_code == 200
        returned_organization = response.data["organisation_name"]
        new_organization_name = update_org_dict["organisation_name"]
        assert returned_organization == new_organization_name

    def test_put_organisation(self):
        """Test complete change of organisation details."""
        org = baker.make(Organisation, organisation_name="Sil Devs")
        update_org_dict = {
            "organisation_name": "Coptic",
            "active": True,
            "created_by": self.user.pk,
            "slade_code": 2001,
            "updated_by": self.user.pk,
            "phone_number": "+254721585473",
            "default_country": "KEN",
            "email_address": "me@me.com",
            "financial_year_start_date": "2016-11-07",
        }
        url = reverse("organisation-detail", kwargs={"pk": org.pk})
        response = self.client.put(url, update_org_dict)

        assert response.status_code == 200
        returned_organization = response.data["organisation_name"]
        new_organization_name = update_org_dict["organisation_name"]
        assert returned_organization == new_organization_name

    def _get_file(self, filename):
        filename = path.join(DIR_PATH, filename)
        with open(filename, "r+b") as myfile:
            read_file = myfile.read()
            memory = SimpleUploadedFile(
                "test_image.jpeg",
                read_file,
                content_type="image/jpeg",
            )
            return memory


class PersonViewTest(LoggedInMixin):
    """Test for the person/user view."""

    def setUp(self):
        """Create a test user."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.url_list = reverse("person-list")
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

    def test_create_persons(self):
        """Test creation of a new person."""
        data = {
            "first_name": "Sheldon",
            "last_name": "Cooper",
            "other_names": "Rajesh",
            "date_of_birth": "2016-05-01",
            "active": "true",
            "deleted": False,
            "organisation": self.global_organisation.pk,
            "person_contacts": [
                {
                    "contact": "+254729372839",
                    "contact_type": "phone_number",
                },
            ],
            "person_ids": [],
            "person_photos": [],
            **self.workstation_data,
        }

        response = self.client.post(self.url_list, data)
        assert response.status_code == 201
        assert response.data["first_name"] == data["first_name"]

    def test_retrieve_person(self):
        """Test addition  of person."""
        baker.make(
            Person,
            first_name="Sheldon",
            organisation=self.global_organisation,
            **self.workstation_data,
        )
        baker.make(
            Person,
            first_name="Cooper",
            organisation=self.global_organisation,
            **self.workstation_data,
        )

        response = self.client.get(self.url_list)
        assert response.data["count"] == 2

        # test retrieve person with query for active items
        baker.make(
            Person,
            active=False,
            **self.workstation_data,
        )
        assert Person.objects.all().count() == 5
        response = self.client.get(self.url_list + "?active=True")
        assert response.data["count"] == 2
        response = self.client.get(self.url_list + "?active=False")
        assert response.data["count"] == 1
        assert response.data["results"][0]["active"] is False
        response = self.client.get(self.url_list + "?active=other")
        assert response.data["count"] == 3

    def test_person_double_registration_with_contact(self):
        """Test person double registration with contact."""
        person = baker.make(
            Person,
            first_name="John",
            last_name="Smith",
            date_of_birth="2016-05-01",
            organisation=self.global_organisation,
        )
        phone_contact = baker.make(
            PersonContact,
            contact="+254729372839",
            contact_type="phone_number",
            is_primary_contact=True,
            person=person,
            organisation=self.global_organisation,
        )

        assert person.first_name == "John"
        assert person.last_name == "Smith"
        assert phone_contact.is_phone_number is True
        data = {
            "first_name": "John",
            "last_name": "Smith",
            "date_of_birth": "2016-05-01",
            "active": "true",
            "deleted": False,
            "organisation": self.global_organisation.pk,
            "person_contacts": [
                {
                    "contact": "+254729372839",
                    "contact_type": "phone_number",
                },
            ],
            "person_ids": [],
            "person_photos": [],
        }
        response = self.client.post(self.url_list, data)
        assert response.status_code == 400
        assert "Person with matching details already exists." in str(response.data)

    def test_person_double_registration_without_contact(self):
        """Test person double registration without contact."""
        person = baker.make(
            Person,
            first_name="John",
            last_name="Smith",
            date_of_birth="2016-05-01",
            organisation=self.global_organisation,
        )

        assert person.first_name == "John"
        assert person.last_name == "Smith"
        assert person.person_contacts.count() == 0
        data = {
            "first_name": "John",
            "last_name": "Smith",
            "date_of_birth": "2016-05-01",
            "active": "true",
            "deleted": False,
            "organisation": self.global_organisation.pk,
            "person_ids": [],
            "person_photos": [],
        }
        response = self.client.post(self.url_list, data)
        assert response.status_code == 400
        assert "Person with matching details already exists." in str(response.data)

    def test_create_person_without_existing_record(self):
        """Test creating a person without an existing record."""
        assert not Person.objects.filter(
            first_name="John", last_name="Doe", date_of_birth="1990-01-01"
        ).exists()

        data = {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-01",
            "active": "true",
            "deleted": False,
            "organisation": self.global_organisation.pk,
            "person_contacts": [],
            "person_ids": [],
            "person_photos": [],
        }

        response = self.client.post(self.url_list, data)

        assert response.status_code == 201
        assert Person.objects.filter(
            first_name="John", last_name="Doe", date_of_birth="1990-01-01"
        ).exists()


class DontPassIdTest(LoggedInMixin):
    """Test suite for getting user using id."""

    def setUp(self):
        """Create person for the test."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.url_list = reverse("person-list")
        super().setUp()

    def test_pass_object_with_id(self):
        """Test error getting person using id."""
        data = {
            "id": "7bda08a7-d399-46bc-b1a5-ad48eedab327",
            "first_name": "Sheldon",
            "last_name": "Cooper",
            "other_names": "Rajesh",
            "gender": "MALE",
            "date_of_birth": "2016-05-01",
            "marital_status": "S",
            "active": "true",
            "deleted": False,
            "organisation": self.global_organisation.pk,
            "person_contacts": [
                {
                    "contact": "+254729372839",
                    "contact_type": "phone_number",
                },
            ],
            "person_ids": [],
            "person_photos": [],
        }

        response = self.client.post(self.url_list, data)
        assert response.status_code == 400
        error_msg = "You are not allowed to pass object with an id"

        assert response.data["id"] == error_msg


class ContactViewTest(LoggedInMixin):
    """Test suite for user contact."""

    def setUp(self):
        """Create person for test."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.url_list = reverse("contacts-list")
        super().setUp()

    def test_retrieve_contact(self):
        """Test retrieving user contact."""
        organisation = self.global_organisation
        contact_type = "phone_number"
        person = baker.make(Person, organisation=organisation)

        baker.make(
            PersonContact,
            contact="+254738273847",
            organisation=organisation,
            person=person,
            contact_type=contact_type,
        )

        baker.make(
            PersonContact,
            contact="+254728472648",
            organisation=organisation,
            person=person,
            contact_type=contact_type,
        )

        response = self.client.get(self.url_list)
        assert response.data["count"] == 2

        contacts = [a["contact"] for a in response.data["results"]]
        assert "+254738273847" in contacts
        assert "+254728472648" in contacts

    def test_patch_contact(self):
        """Test changing user contact."""
        organisation = self.global_organisation
        person = baker.make(Person, organisation=organisation)
        contact_type = "phone_number"
        contact = "+2540728465837"
        contact = baker.make(
            PersonContact,
            organisation=organisation,
            person=person,
            contact_type=contact_type,
            contact=contact,
        )
        edit_contact = {"contact": "+254739282918"}
        url = reverse("contacts-detail", kwargs={"pk": contact.pk})
        response = self.client.patch(url, edit_contact)

        assert response.status_code == 200
        assert response.data["contact"] == edit_contact["contact"]

    def test_put_contact(self):
        """Test changing user and add new contact."""
        organisation = self.global_organisation
        person = baker.make(Person, organisation=organisation)
        contact_type = "phone_number"
        contact = "+2540728465837"
        contact = baker.make(
            PersonContact,
            organisation=organisation,
            person=person,
            contact_type=contact_type,
            contact=contact,
        )
        data = {
            "contact_type": contact_type,
            "person": person.pk,
            "organisation": organisation.pk,
            "contact": "+2540728465837",
            "active": True,
            "deleted": False,
        }

        url = reverse("contacts-detail", kwargs={"pk": contact.pk})
        response = self.client.put(url, data)

        assert response.status_code == 200
        assert response.data["contact"] == data["contact"]


class PersonIDViewTest(LoggedInMixin):
    """Test for User ID view."""

    def setUp(self):
        """Create test user."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.url_list = reverse("personid-list")
        super().setUp()

    def test_retrieve_user_id(self):
        """Test retrieval of user id."""
        org = self.global_organisation
        doc_type = "nationalID"
        person = baker.make(Person, organisation=org)
        baker.make(
            PersonID,
            id_value="00000000",
            organisation=org,
            person=person,
            id_document_type=doc_type,
        )
        baker.make(
            PersonID,
            id_value="00000001",
            organisation=org,
            person=person,
            id_document_type=doc_type,
        )

        response = self.client.get(self.url_list)
        assert response.data["count"] == 2

        contacts = [a["id_value"] for a in response.data["results"]]
        assert "00000000" in contacts
        assert "00000001" in contacts

    def test_patch_user_id(self):
        """Test changing of user id."""
        organisation = self.global_organisation
        doc_type = "nationalID"
        person = baker.make(Person, organisation=organisation)
        user_id = baker.make(
            PersonID,
            id_value="00000000",
            organisation=organisation,
            person=person,
            id_document_type=doc_type,
        )

        edit_id = {"id_value": "00000001"}
        url = reverse("personid-detail", kwargs={"pk": user_id.pk})
        response = self.client.patch(url, edit_id)

        assert response.status_code == 200
        assert response.data["id_value"] == edit_id["id_value"]

    def test_put_user_id(self):
        """Test changing user id."""
        organisation = self.global_organisation
        doc_type = "nationalID"
        person = baker.make(Person, organisation=organisation)
        user_id = baker.make(
            PersonID,
            id_value="00000000",
            organisation=organisation,
            person=person,
            id_document_type=doc_type,
        )

        data = {
            "person": person.pk,
            "id_document_type": doc_type,
            "organisation": organisation.pk,
            "id_value": "98473838",
            "deleted": False,
        }

        url = reverse("personid-detail", kwargs={"pk": user_id.pk})
        response = self.client.put(url, data)

        assert response.status_code == 200
        assert response.data["id_value"] == data["id_value"]


class ConsentViewTest(LoggedInMixin):
    """Test for User ID view."""

    def setUp(self):
        """Create test user."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")

        super().setUp()

    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_send_otp(self, mock_send_sms):
        """Test sending a consent OTP."""
        organisation = self.global_organisation
        person = baker.make(Person, organisation=organisation)
        consent = baker.make(
            Consent,
            person=person,
            organisation=organisation,
            consent_type=ConsentType.SMS_COMMUNICATION,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        baker.make(
            PersonContact,
            contact="+254722385672",
            contact_type="phone_number",
            person=person,
            organisation=organisation,
        )

        url = reverse("consent-send-otp", kwargs={"pk": consent.id})
        response = self.client.post(url)

        assert response.status_code == 200

        consent.refresh_from_db()
        assert consent.otp is not None

        # test send otp for other consent types
        mock_send_sms.reset_mock()
        consent = baker.make(
            Consent,
            person=person,
            organisation=organisation,
            consent_type=ConsentType.SMS_HEALTH_EDUCATION,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        url = reverse("consent-send-otp", kwargs={"pk": consent.id})
        response = self.client.post(url)

        consent.refresh_from_db()
        mock_send_sms.assert_called_once_with(
            queue="advantage_tasks",
            priority=5,
            args=(
                "OTP",
                (
                    f"Hi {person.first_name}, your consent verification code is "
                    f"{consent.otp.code}. Never share this code."
                ),
                ["+254722385672"],
                organisation.slade_code,
                person.branch_id,
                person.workstation_id,
            ),
        )

        assert response.status_code == 200

        url = reverse("consent-list")
        response = self.client.get(url + f"?person={str(person.id)}")
        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["updated_by_name"] == "John Doe"

    def test_verify_otp(self):
        """Test verifying a consent OTP."""
        organisation = self.global_organisation
        person = baker.make(Person, organisation=organisation)

        otp = baker.make(
            PersonOTP,
            person=person,
            code="354658",
            verification_status=OTPVerificationStatus.PENDING,
            expires_at=None,
        )

        consent = baker.make(
            Consent,
            person=person,
            organisation=organisation,
            consent_type=ConsentType.SMS_COMMUNICATION,
            otp=otp,
            status=ConsentStatus.PENDING,
        )

        url = reverse("consent-verify-otp", kwargs={"pk": consent.id})
        response = self.client.post(url, data={"code": "354658"})

        assert response.status_code == 200
        assert response.data["status"] == OTPVerificationStatus.VERIFIED

        otp.refresh_from_db()
        assert otp.verification_status == OTPVerificationStatus.VERIFIED

    def test_verify_otp_expired_code(self):
        """Test verifying a consent OTP with an expired code."""
        organisation = self.global_organisation
        person = baker.make(Person, organisation=organisation)

        otp = baker.make(
            PersonOTP,
            person=person,
            code="354658",
            verification_status=OTPVerificationStatus.PENDING,
            expires_at=timezone.now() - timedelta(days=1),
        )

        consent = baker.make(
            Consent,
            person=person,
            organisation=organisation,
            consent_type=ConsentType.SMS_COMMUNICATION,
            otp=otp,
            status=ConsentStatus.PENDING,
        )

        url = reverse("consent-verify-otp", kwargs={"pk": consent.id})
        response = self.client.post(url, data={"code": "354658"})

        assert response.status_code == 400
        consent.refresh_from_db()

        assert consent.status == ConsentStatus.PENDING
        assert consent.consent_logs.count() == 0

        otp.refresh_from_db()
        assert otp.verification_status == OTPVerificationStatus.PENDING

    def test_verify_otp_verified_code(self):
        """Test verifying a consent OTP that is already verified."""
        organisation = self.global_organisation
        person = baker.make(Person, organisation=organisation)

        otp = baker.make(
            PersonOTP,
            person=person,
            code="354658",
            verification_status=OTPVerificationStatus.VERIFIED,
        )

        consent = baker.make(
            Consent,
            person=person,
            organisation=organisation,
            consent_type=ConsentType.SMS_COMMUNICATION,
            otp=otp,
            status=ConsentStatus.PENDING,
        )

        url = reverse("consent-verify-otp", kwargs={"pk": consent.id})
        response = self.client.post(url, data={"code": "354658"})

        assert response.status_code == 400
        consent.refresh_from_db()

        assert consent.status == ConsentStatus.PENDING
        assert consent.consent_logs.count() == 0

        otp.refresh_from_db()
        assert otp.verification_status == OTPVerificationStatus.VERIFIED

    def test_verify_otp_wrong_code(self):
        """Test verifying a consent OTP that is wrong."""
        organisation = self.global_organisation
        person = baker.make(Person, organisation=organisation)

        otp = baker.make(
            PersonOTP,
            person=person,
            code="354658",
            verification_status=OTPVerificationStatus.PENDING,
        )

        consent = baker.make(
            Consent,
            person=person,
            organisation=organisation,
            consent_type=ConsentType.SMS_COMMUNICATION,
            otp=otp,
            status=ConsentStatus.PENDING,
        )

        url = reverse("consent-verify-otp", kwargs={"pk": consent.id})
        response = self.client.post(url, data={"code": "354358"})

        assert response.status_code == 400
        consent.refresh_from_db()

        assert consent.status == ConsentStatus.PENDING
        assert consent.consent_logs.count() == 0

        otp.refresh_from_db()
        assert otp.verification_status == OTPVerificationStatus.PENDING


class ConsentTransitionViewTest(LoggedInMixin):
    """Test for User ID view."""

    def setUp(self):
        """Create test user."""
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        super().setUp()

    def test_send_otp(self):
        """Test sending a consent OTP."""
        organisation = self.global_organisation
        person = baker.make(Person, organisation=organisation)
        consent = baker.make(
            Consent,
            person=person,
            organisation=organisation,
            consent_type=ConsentType.SMS_COMMUNICATION,
        )

        assert consent.consent_logs.count() == 0

        url = reverse(
            "consent-transition",
            kwargs={"id": consent.id, "status": ConsentStatus.VERIFIED},
        )
        response = self.client.patch(url)

        assert response.status_code == 200

        consent.refresh_from_db()
        assert consent.status == ConsentStatus.VERIFIED
        assert consent.consent_logs.count() == 1


class OperatingRegionTests(LoggedInMixin):
    """Test for OperatingRegion view."""

    def setUp(self):
        """Initial setup for the test case."""
        super().setUp()
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.organisation = self.global_organisation
        self.operating_region_data = {
            "name": "Test Region",
            "unit_type": "COUNTY",
            "country": "KEN",
            "created_by": self.user.pk,
            "updated_by": self.user.pk,
            "organisation": self.organisation,
            "heirachy_structure": {"level1": "Unit A", "level2": "Unit B"},
        }
        self.operating_region = OperatingRegion.objects.create(
            **self.operating_region_data
        )
        self.list_url = reverse("operatingregion-list")
        self.detail_url = reverse(
            "operatingregion-detail", kwargs={"pk": self.operating_region.pk}
        )

    def test_list_operating_regions(self):
        """Test listing OperatingRegions."""
        response = self.client.get(self.list_url, format="json")
        self.assertEqual(response.status_code, 200)

    def test_retrieve_operating_region(self):
        """Test retrieving a single OperatingRegion."""
        response = self.client.get(self.detail_url, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], self.operating_region.name)

    def test_update_operating_region(self):
        """Test updating an OperatingRegion."""
        updated_data = {
            "name": "Updated Region",
            "unit_type": "COUNTY",
            "country": "KEN",
            "created_by": self.user.pk,
            "updated_by": self.user.pk,
            "organisation": self.organisation.id,
            "heirachy_structure": {
                "level1": "Updated Unit A",
                "level2": "Updated Unit B",
            },
        }
        response = self.client.put(self.detail_url, updated_data, format="json")
        self.assertEqual(response.status_code, 200)
        self.operating_region.refresh_from_db()
        self.assertEqual(self.operating_region.name, "Updated Region")
        self.assertEqual(
            self.operating_region.heirachy_structure["level1"], "Updated Unit A"
        )

    def test_partial_update_operating_region(self):
        """Test partially updating an OperatingRegion."""
        updated_data = {"name": "Partially Updated Region"}
        response = self.client.patch(self.detail_url, updated_data, format="json")
        self.assertEqual(response.status_code, 200)
        self.operating_region.refresh_from_db()
        self.assertEqual(self.operating_region.name, "Partially Updated Region")

    def test_delete_operating_region(self):
        """Test deleting an OperatingRegion."""
        response = self.client.delete(self.detail_url, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(OperatingRegion.objects.count(), 0)

    def test_create_operating_region(self):
        """Test creating an OperatingRegion."""
        data = {
            "name": "New Region",
            "created_by": self.user.pk,
            "updated_by": self.user.pk,
            "organisation": self.organisation.id,
            "unit_type": "COUNTY",
            "country": "RWA",
            "heirachy_structure": {"level1": "Unit C", "level2": "Unit D"},
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(OperatingRegion.objects.count(), 2)
        self.assertEqual(
            OperatingRegion.objects.get(id=response.data["id"]).name, "New Region"
        )

    def test_search_by_name(self):
        """Test searching OperatingRegions by name."""
        response = self.client.get(
            self.list_url, {"search": "Test Region"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["name"], "Test Region")

    def test_search_by_country(self):
        """Test searching OperatingRegions by country."""
        response = self.client.get(self.list_url, {"search": "KEN"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["country"], "KEN")

    def test_search_by_unit_type(self):
        """Test searching OperatingRegions by unit type."""
        response = self.client.get(self.list_url, {"search": "COUNTY"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["unit_type"], "COUNTY")

    def test_search_no_results(self):
        """Test searching OperatingRegions with no results."""
        response = self.client.get(
            self.list_url, {"search": "Nonexistent"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 0)

    def test_filter_heirachy_structure(self):
        """Test filtering OperatingRegions by heirachy_structure level1."""
        response = self.client.get(
            self.list_url, {"heirachy_structure": "Unit A"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["name"], "Test Region")


class TestPersonContactViewSet(LoggedInMixin):
    """Test for person/contact viewset."""

    def setUp(self):
        """Set up the test environment."""
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.url = reverse("contacts-list")
        self.workstation_data = {
            "cluster_id": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "branch_id": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "department_id": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "workstation_id": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

        self.person = baker.make(
            Person,
            organisation=self.global_organisation,
            first_name="Martin",
            last_name="Luther",
            **self.workstation_data,
        )
        super().setUp()

    def extra_headers(self):
        """Workstation headers."""
        return {
            "X-Cluster": "cc90d9b5-b285-433e-9a83-97f93b50885c",
            "X-Branch": "9f273420-b325-475c-a1a5-0dd268eeffb1",
            "X-Department": "d8cf4e72-927b-46aa-a251-76a5a91f8343",
            "X-Workstation": "77df295d-c434-48d0-bf6c-3995f5fbbfe3",
        }

    def test_person_contact(self):
        """Test for creating, reading, and updating a person contact."""
        payload1 = {
            "person": self.person.id,
            "contact_type": "phone_number",
            "contact": "+254729372839",
            "verified": True,
            "is_primary": True,
            "consent_to_contact_give": False,
        }
        response = self.client.post(self.url, payload1)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["contact_type"], "phone_number")
        self.assertEqual(response.data["contact"], "+254729372839")
        self.assertEqual(PersonContact.objects.count(), 1)

        payload2 = {
            "person": self.person.id,
            "contact_type": "email",
            "contact": "luther@savannah.com",
            "verified": True,
            "is_primary": True,
            "consent_to_contact_give": False,
        }
        response = self.client.post(self.url, payload2)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["contact_type"], "email")
        self.assertEqual(response.data["contact"], "luther@savannah.com")
        self.assertEqual(PersonContact.objects.count(), 2)

        # list view
        list_response = self.client.get(self.url)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data["count"], 2)

        # Detail view
        id = list_response.data["results"][0]["id"]
        person_contact = PersonContact.objects.get(id=id)
        detail_url = reverse("contacts-detail", kwargs={"pk": person_contact.pk})
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)

        # Update view
        payload3 = {
            "contact": "martin@savannah.com",
        }
        update_response = self.client.patch(detail_url, data=payload3)
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data["contact"], payload3["contact"])

    def test_delete_person_contact(self):
        """Test for deleting a person contact."""
        person_contact = baker.make(
            PersonContact,
            person=self.person,
            organisation=self.global_organisation,
            contact_type="phone_number",
            contact="+254738273847",
        )
        self.assertEqual(PersonContact.objects.count(), 1)
        url = reverse("contacts-detail", kwargs={"pk": person_contact.pk})
        response = self.client.delete(url, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(PersonContact.objects.count(), 0)
