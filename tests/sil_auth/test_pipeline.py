"""Tests for auth pipelines."""
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from model_bakery import baker
from rest_framework.exceptions import PermissionDenied
from rest_framework.serializers import ValidationError
from rest_framework.test import APITestCase
from social_django.models import UserSocialAuth

from sil_advantage.common.models import Organisation, Person, UserProfile
from sil_advantage.sil_auth.pipeline import (
    convert_permissions_to_string,
    create_person,
    create_user_profile,
    fetch_user,
)
from tests.common.utility import patch_baker

USER_MODEL = get_user_model()

MOCK_ROOT = "sil_advantage.sil_auth.pipeline."


class TestCreatePersonPipeline(APITestCase):
    """Test case for pipeline.

    This class tests the working of the methods and leaves the
    sematics of calling the pipeline to ``python-social-auth``
    """

    def setUp(self):
        """Test set up."""
        self.user = baker.make(USER_MODEL)
        self.org = baker.make(Organisation, slade_code=500)
        self.extra_data = {
            "first_name": "first_name",
            "last_name": "last_name",
            "organisation": str(self.org.id),
            "business_partner": str(self.org.slade_code),
        }
        self.social = UserSocialAuth.objects.create(
            uid=self.user.id, user=self.user, extra_data=self.extra_data
        )
        super().setUp()
        values = {"created_by": self.user.pk, "updated_by": self.user.pk}

        patcher = patch_baker(values=values)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_create_person(self):
        """Test create a person."""
        assert Person.objects.count() == 0
        res = create_person(self.user, self.social, is_new=True)
        person = res["person"]

        assert person.first_name == "first_name"
        assert Person.objects.count() == 1

    def test_create_person_business_partner_required(self):
        """Test validate create a person business partner.

        To create a person record you must provide an organisation.
        """
        user = baker.make(USER_MODEL)
        self.extra_data.pop("business_partner")
        social = UserSocialAuth.objects.create(
            uid=user.id, user=user, extra_data=self.extra_data
        )
        with pytest.raises(ValidationError):
            create_person(self.user, social, is_new=True)

    def test_throws_perm_denied(self):
        """Test denied permission.

        Permission denied error is thrown if the organisation is inactive
        """
        self.org.active = False
        self.org.note = "Changing State"
        self.org.save()
        with pytest.raises(PermissionDenied) as e:
            create_person(self.user, self.social, is_new=True)
        assert str(e.value) == "Inactive Organisation"

    def test_create_person_already_exists(self):
        """Test validate a person.

        A person is not created if the person in question already exists
        """
        person_rec = baker.make(Person)
        user = baker.make(USER_MODEL)
        key = f"user_update_lock_{self.user.id}"
        cache.set(key, True)
        UserProfile.objects.create(
            user=self.user,
            person=person_rec,
            organisation=person_rec.organisation,
            created_by=user.pk,
            updated_by=user.pk,
        )
        assert Person.objects.count() == 1
        res = create_person(self.user, self.social, is_new=False)
        person = res["person"]
        assert person.id == person_rec.id
        assert Person.objects.count() == 1
        cache.delete(key)

    def test_create_person_already_exists_needs_update(self):
        """Test validate a person (needs update)."""
        person_rec = baker.make(Person)
        user = baker.make(USER_MODEL)
        UserProfile.objects.create(
            user=self.user,
            person=person_rec,
            organisation=person_rec.organisation,
            created_by=user.pk,
            updated_by=user.pk,
        )
        assert Person.objects.count() == 1
        res = create_person(self.user, self.social, is_new=False)
        person = res["person"]
        assert person.id == person_rec.id
        assert Person.objects.count() == 1

    def test_create_person_rollback(self):
        """Test undo creating a person.

        Changes made to ``UserSocialAuth`` and the user are rolled-back if
        the ``Person`` model cannot be created
        """
        user = baker.make(USER_MODEL)
        self.extra_data.pop("business_partner")
        social = UserSocialAuth.objects.create(
            uid=user.id, user=user, extra_data=self.extra_data
        )

        with pytest.raises(ValidationError):
            create_person(user, social, is_new=True)
            assert USER_MODEL.objects.filter(id=user.id).exists() is False
            assert UserSocialAuth.objects.filter(id=social.id).exists() is False


class TestCreateUserProfilePipeline(APITestCase):
    """Test case for user profile pipeline.

    Test that a userprofile is created for a particular user. This happens
    in the ``python-social-auth`` pipeline after a ``Person`` is created
    """

    def setUp(self):
        """Test set up."""
        self.user = baker.make(USER_MODEL)
        self.org = baker.make(Organisation)
        self.person = baker.make(Person, organisation=self.org)
        super().setUp()

    def test_create_user_profile(self):
        """Test create a user profile."""
        assert UserProfile.objects.count() == 0
        res = create_user_profile(self.user, self.person, is_new=True)
        user_profile = res["user_profile"]
        assert UserProfile.objects.count() == 1
        assert user_profile.person.id == self.person.id
        assert user_profile.user.id == self.user.id

    def test_create_user_profile_already_existed(self):
        """Test validate create a user profile.

        If a user-profile for the user already exists. No new profiles are
        created and instead the old one is used.
        """
        UserProfile.objects.create(
            user=self.user,
            organisation=self.org,
            person=self.person,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        assert UserProfile.objects.count() == 1
        res = create_user_profile(self.user, self.person, is_new=False)
        assert UserProfile.objects.count() == 1
        assert res == {}

    def test_fetch_user_is_not_found(self):
        """Test retrieve invalid user."""
        uid = uuid.uuid4()
        response = fetch_user(uid)

        assert response["user"] is None

    def test_fetch_user_is_found(self):
        """Test retrieve a user."""
        import uuid

        uid = uuid.uuid4()
        baker.make(USER_MODEL, guid=uid)
        response = fetch_user(uid)

        assert response["user"].guid == uid


class TestConvertPermsToString(APITestCase):
    """Test case convert permissions."""

    def test_converts_perms_array_to_string(self):
        """Test convert to a comma separated list."""
        details = {"permissions": ["perm", "zote"]}

        res = convert_permissions_to_string(details)

        assert res["details"]["permissions"] == "perm,zote"

    def test_returns_details_perms_not_present(self):
        """Test convert to a list."""
        details = {"test": "test-data"}

        res = convert_permissions_to_string(details)
        assert len(res["details"].keys()) == 1
        assert res["details"]["test"] == "test-data"
