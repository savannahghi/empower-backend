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
