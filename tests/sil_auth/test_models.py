"""Test authentication models."""
import time
import uuid

import pyotp
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from model_bakery import baker

from sil_advantage.common.models import (
    Person,
    PersonContact,
    PersonOTP,
    UserProfile,
)
from sil_advantage.sil_auth.models import MFAStatus, MFAType, SILUserMFA
from tests.common.test_common_views import global_organisation


class SILUserTest(TestCase):
    """Test case for the user model."""

    def test_unicode(self):
        """Test email is a string."""
        user = baker.make(get_user_model(), email="test@tester.com")
        assert str(user) == "test@tester.com"

    def test_get_full_name(self):
        """Test user full name."""
        self.organisation = global_organisation()
        self.person = baker.make(Person, first_name="Sheldon", last_name="Cooper")
        self.user = baker.make(
            get_user_model(), email="test@tester.com", guid=uuid.uuid4()
        )
        self.user_profile = baker.make(
            UserProfile,
            user=self.user,
            person=self.person,
            organisation=self.organisation,
        )
        assert self.user.get_full_name() == "Sheldon Cooper"
        assert self.user.full_name == "Sheldon Cooper"

    def test_get_full_name_with_missing_profile(self):
        """Test full name from a missing user profile."""
        self.user = baker.make(
            get_user_model(), email="test@tester.com", guid=uuid.uuid4()
        )

        assert self.user.get_full_name() is None

    def test_get_perms(self):
        """Test users permissions are returned."""
        user = get_user_model().objects.create_user(
            guid=uuid.uuid4(),
            email="mail@mail.com",
            password="pass123",
            permissions="list_organisation,create_organistioin",
        )

        assert 2 == len(user.permissions.split(","))
        assert "list_organisation" == user.permissions.split(",")[0]

    def test_has_perms_successful(self):
        """Test user permissions."""
        user = get_user_model().objects.create_user(
            guid=uuid.uuid4(),
            email="mail@mail.com",
            password="pass123",
            permissions="list_organisation,create_organistioin",
        )

        assert user.has_permissions(["list_organisation"])

    def test_has_perms_failure(self):
        """Test user permissions."""
        user = get_user_model().objects.create_user(
            guid=uuid.uuid4(),
            email="mail@mail.com",
            password="pass123",
            permissions="",
        )

        assert not user.has_permissions(["list_organisation"])

    def test_get_perms_without_perms(self):
        """Test user without permissions."""
        user = get_user_model().objects.create_user(
            guid=uuid.uuid4(), email="mail@mail.com", password="pass123"
        )

        assert user.permissions == ""

    def test_delete_user(self):
        """Test delete a server user."""
        user = baker.make(get_user_model(), _quantity=5, guid=lambda: uuid.uuid4())
        assert get_user_model().objects.count() == 5
        user[0].delete()
        assert get_user_model().objects.count() == 4


def test_create_phone_otp_mfa(organisation):
    """Test phone MFA creation for a user."""
    user = baker.make(
        get_user_model(), email="gaines.edmund@them.show", guid=uuid.uuid4()
    )
    person = baker.make(
        Person, first_name="Edmund", last_name="Gaines", organisation=organisation
    )
    baker.make(
        PersonContact,
        person=person,
        contact_type="phone_number",
        contact="+254722060000",
    )

    baker.make(
        UserProfile,
        user=user,
        person=person,
        organisation=organisation,
    )

    assert user.mfa_methods.count() == 0

    phone_mfa = baker.make(SILUserMFA, mfa_type=MFAType.PHONE_OTP, user=user)

    assert phone_mfa.status == MFAStatus.PENDING
    assert user.mfa_methods.count() == 1

    user_mfa = user.mfa_methods.first()

    assert user_mfa.mfa_type == MFAType.PHONE_OTP

    phone_mfa.refresh_from_db()
    assert phone_mfa.id == user_mfa.id
    assert phone_mfa in user.user_mfa_methods
    assert phone_mfa.totp_provisioning_uri is None


def test_validate_create_phone_otp_mfa_without_phone_number(organisation):
    """Test phone MFA creation for a user without phone number."""
    user = baker.make(get_user_model(), email="reeve.dawn@them.show", guid=uuid.uuid4())
    person = baker.make(
        Person, first_name="Dawn", last_name="Reeve", organisation=organisation
    )

    baker.make(
        UserProfile,
        user=user,
        person=person,
        organisation=organisation,
    )

    assert user.mfa_methods.count() == 0

    with pytest.raises(ValidationError) as e:
        baker.make(SILUserMFA, mfa_type=MFAType.PHONE_OTP, user=user)

    assert e.value.message_dict == {
        "phone number": ["A phone number is required to add this MFA."]
    }
    assert user.mfa_methods.count() == 0


def test_create_totp_mfa(organisation):
    """Test creating a TOTP MFA."""
    user = baker.make(get_user_model(), email="reeve.dawn@them.show", guid=uuid.uuid4())
    person = baker.make(
        Person, first_name="Dawn", last_name="Reeve", organisation=organisation
    )

    baker.make(
        UserProfile,
        user=user,
        person=person,
        organisation=organisation,
    )

    assert user.mfa_methods.count() == 0

    totp_mfa = baker.make(SILUserMFA, mfa_type=MFAType.TOTP, user=user)

    assert totp_mfa.status == MFAStatus.PENDING
    assert user.mfa_methods.count() == 1

    user_mfa = user.mfa_methods.first()

    assert user_mfa.mfa_type == MFAType.TOTP

    totp_mfa.refresh_from_db()

    assert totp_mfa.id == user_mfa.id
    assert totp_mfa in user.user_mfa_methods
    assert totp_mfa.secret_key is not None
    assert totp_mfa.totp_provisioning_uri is not None


def test_mfa_verify_otp_code(organisation, organisation_user):
    """Test verifying an OTP code."""
    user = baker.make(get_user_model(), email="reeve.dawn@them.show", guid=uuid.uuid4())
    person = baker.make(
        Person, first_name="Dawn", last_name="Reeve", organisation=organisation
    )
    baker.make(
        PersonContact,
        person=person,
        contact_type="phone_number",
        contact="+254722060000",
    )

    baker.make(
        UserProfile,
        user=user,
        person=person,
        organisation=organisation,
    )

    phone_mfa = baker.make(SILUserMFA, mfa_type=MFAType.PHONE_OTP, user=user)

    assert phone_mfa.verify_otp_code("123456") is False

    otp = baker.make(
        PersonOTP, organisation=organisation, created_by=organisation_user.id
    )
    phone_mfa.otp = otp
    phone_mfa.save()

    with pytest.raises(ValidationError):
        assert phone_mfa.verify_otp_code("123456")

    assert phone_mfa.verify_otp_code(otp.code) is True

    totp_mfa = baker.make(SILUserMFA, mfa_type=MFAType.TOTP, user=user)

    totp = pyotp.TOTP(totp_mfa.secret_key).now()

    assert totp_mfa.verify_otp_code(totp) is True

    # totp expires after 30s
    time.sleep(30)
    with pytest.raises(ValidationError):
        assert totp_mfa.verify_otp_code(totp)
