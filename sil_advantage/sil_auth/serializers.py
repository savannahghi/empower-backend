"""Authentication serializers."""
from typing import Any, Optional
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from sil_advantage.common.models import (
    Organisation,
    OrganisationOnboarding,
    OrgUnit,
    Person,
    UserProfile,
)
from sil_advantage.common.serializers import (
    BaseSerializer,
    PersonSerializer,
    UserProfileSerializer,
    get_organisation,
)
from sil_advantage.notifications.matrix import (
    get_matrix_access_token,
    set_matrix_display_name,
)
from sil_advantage.sil_auth.models import SILUser, SILUserMFA


class UserMFASerializer(BaseSerializer):
    """Serializer for user MFA."""

    totp_provisioning_uri = serializers.CharField(read_only=True, required=False)

    class Meta:
        """User MFA Serializer Meta Class."""

        model = SILUserMFA
        fields = ["id", "user", "mfa_type", "status", "totp_provisioning_uri"]


class UserSerializer(BaseSerializer):
    """Serialize user details."""

    pk = serializers.ReadOnlyField(read_only=True)
    gender_name = serializers.ReadOnlyField(source="person.gender.display")
    first_name = serializers.ReadOnlyField(source="person.first_name")
    last_name = serializers.ReadOnlyField(source="person.last_name")
    full_name = serializers.ReadOnlyField()
    person_id = serializers.ReadOnlyField(source="person.id")
    phone_number = serializers.CharField(
        read_only=True, required=False, source="person.phone_number"
    )
    organisation_id = serializers.ReadOnlyField(source="organisation.id")
    organisation_name = serializers.ReadOnlyField(
        source="organisation.organisation_name"
    )
    slade_code = serializers.ReadOnlyField(source="organisation.slade_code")
    organisation_email_address = serializers.ReadOnlyField(
        source="organisation.email_address"
    )
    organisation_onboarding = serializers.SerializerMethodField()

    # Clinical Service
    clinical_org_id = serializers.ReadOnlyField(
        source="organisation.tenant_id",
    )
    clinical_facility_id = serializers.SerializerMethodField()

    # Matrix
    matrix_token = serializers.SerializerMethodField()

    # MFA
    user_mfa_methods = UserMFASerializer(many=True, read_only=True, required=False)

    def get_clinical_facility_id(self, instance: SILUser) -> Optional[UUID]:
        """Get the facility ID."""
        request = self.context["request"]
        branch_id = request.META.get(
            "HTTP_X_BRANCH", request.META.get("X-Branch", None)
        )
        try:
            unit = OrgUnit.objects.get(
                organisation=instance.organisation,
                erp_id=branch_id,
                orgunit_type="branch",
            )
            facility_id = unit.facility_id
        except OrgUnit.DoesNotExist:
            facility_id = None
        return facility_id

    def get_matrix_token(self, instance: SILUser) -> dict:
        """Get the Matrix access token."""
        try:
            token = get_matrix_access_token(instance.guid)
            if instance.matrix_user_id is None:
                instance.matrix_user_id = token["user_id"]
                instance.save(update_fields=["matrix_user_id"])
                set_matrix_display_name(instance)
        except Exception:
            # Prevent Matrix errors from killing /me endpoint
            token = locals().get("token", None)
        return token

    def get_organisation_onboarding(self, instance: SILUser) -> Optional[dict]:
        """Get OrganisationOnboarding instance."""
        try:
            onboarding = OrganisationOnboarding.objects.get(
                organisation=instance.organisation
            )
            payload = {
                "status": onboarding.verification_status,
                "session_level": onboarding.onboarding_session_level,
                "id": onboarding.id,
            }
            return payload
        except OrganisationOnboarding.DoesNotExist:
            return None

    class Meta:
        """User model constraints."""

        model = get_user_model()
        extra_kwargs = {"password": {"write_only": True, "required": False}}
        fields = "__all__"
        read_only_fields = ("last_login",)

    def _validate_person_update(
        self,
        first_name: str,
        last_name: str,
        person: Person,
        org: Organisation,
        context: dict[str, Any],
    ) -> None:
        """Validate person update of first_name and last_name."""
        data: dict[str, UUID | str] = {"organisation": org.pk}
        if first_name:
            data["first_name"] = first_name

        if last_name:
            data["last_name"] = last_name

        if first_name or last_name:
            serializer = PersonSerializer(
                person, data=data, context=context, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

    def _validate_person(
        self,
        first_name: str,
        last_name: str,
        org: Organisation,
        context: dict[str, Any],
    ) -> Person:
        """Check if the `first_name` and `last_name` are provided."""
        person_data = {
            "first_name": first_name,
            "last_name": last_name,
            "organisation": org.pk,
            "person_contacts": [],
            "person_ids": [],
            "person_photos": [],
        }
        serializer = PersonSerializer(data=person_data, context=context)
        serializer.is_valid(raise_exception=True)
        person = serializer.save()
        return person

    def _create_user_profile(
        self,
        person: Person,
        user: SILUser,
        org: Organisation,
        context: dict[str, Any],
    ) -> UserProfile:
        """Create a user profile."""
        data = {
            "user": user.pk,
            "person": person.pk,
            "organisation": org.pk,
        }
        serializer = UserProfileSerializer(data=data, context=context)
        serializer.is_valid(raise_exception=True)
        user_profile = serializer.save()
        return user_profile

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> SILUser:
        """Create a user and their corresponding profile/person."""
        request = self.context["request"]
        org = get_organisation(request)
        password = validated_data.pop("password", None)
        context = self.context
        first_name = self.initial_data.pop("first_name", "")
        last_name = self.initial_data.pop("last_name", "")
        client_url = self.context["request"].META["HTTP_ORIGIN"]

        user = get_user_model().objects.create_user(**validated_data)
        person = self._validate_person(
            first_name,
            last_name,
            org,
            context,
        )
        self._create_user_profile(person, user, org, context)
        user.email_account_details(password, client_url)

        return user

    @transaction.atomic
    def update(
        self,
        instance: SILUser,
        validated_data: dict[str, Any],
    ) -> SILUser:
        """Update a user and their linked person."""
        context = self.context
        request = context["request"]
        org = get_organisation(request, validated_data)
        first_name = self.initial_data.pop("first_name", "")
        last_name = self.initial_data.pop("last_name", "")
        person_id = instance.person
        self._validate_person_update(
            first_name,
            last_name,
            person_id,
            org,
            context,
        )
        return super().update(instance, validated_data)
