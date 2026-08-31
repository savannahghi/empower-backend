"""Onboarding serializers."""
from django.core.validators import EmailValidator
from rest_framework import serializers

from sil_advantage.common import models
from sil_advantage.common.serializers import BaseSerializer


class ProviderInputSerializer(serializers.Serializer):
    """Provider serializer used during signup."""

    name = serializers.CharField()
    slade_code = serializers.CharField(required=False)
    country_id = serializers.UUIDField(
        required=False, help_text="Country ID obtained from chargemaster"
    )


class RegistrationSerializer(serializers.Serializer):
    """Special serializer for Provider and Practioner creation.

    This happens in congruous with fabrication of Organisation Admin.
    """

    provider = ProviderInputSerializer()
    email = serializers.EmailField(validators=[EmailValidator()])
    phone_number = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    password = serializers.CharField()
    confirm_password = serializers.CharField()
    agreed_to_terms = serializers.BooleanField()


class OrganisationOnboardingSerializer(BaseSerializer):
    """Onboarding user preferences serializer for questions."""

    class Meta:
        """Define serialization options."""

        model = models.OrganisationOnboarding
        fields = "__all__"


class FacilityOwnerSerializer(serializers.Serializer):
    """The person registering the facility, who becomes its first admin."""

    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField(validators=[EmailValidator()])
    phone = serializers.CharField(required=False, allow_blank=True)
    role = serializers.CharField(required=False, allow_blank=True)


class FacilityIdentifierSerializer(serializers.Serializer):
    """An external identifier for the facility, such as an MFL code."""

    identifier_type = serializers.CharField()
    identifier_value = serializers.CharField()


class FacilityRegistrationSerializer(serializers.Serializer):
    """Self-service registration of a facility and its first admin.

    Mirrors the payload the sign-up screen already sends.
    """

    name = serializers.CharField()
    owner = FacilityOwnerSerializer()
    county = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    facility_type = serializers.CharField(required=False, allow_blank=True)
    country = serializers.CharField(required=False, allow_blank=True)
    categories = serializers.ListField(required=False)
    identifiers = FacilityIdentifierSerializer(many=True, required=False)
