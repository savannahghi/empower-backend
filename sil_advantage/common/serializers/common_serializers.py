"""Shared serializers and serialization utilities."""
from typing import Optional

from rest_framework import serializers

from sil_advantage.common import models
from sil_advantage.common.constants import RELATIONSHIP_DISPLAYS, RELATIONSHIPS
from sil_advantage.common.serializers import (
    BaseSerializer,
    WritabledNestedBaseSerializer,
)
from sil_advantage.common.utilities.fields import PhoneNumberFieldSerializer


class OrgTransitionLogSerializer(serializers.ModelSerializer):
    """Serialize organisation transition logs."""

    class Meta:
        """Define serialization options."""

        model = models.OrganisationTransitionLog
        fields = "__all__"


class OrganisationSerializer(BaseSerializer):
    """Special serializer for Organisation, which does not inherit AbstractBase.

    Organisation does not use BaseSerializer as as the model does not
    inherit the base model.
    """

    phone_number = PhoneNumberFieldSerializer()

    class Meta:
        """Define organisation serialization options."""

        model = models.Organisation
        fields = "__all__"


class PersonContactSerializer(BaseSerializer):
    """Serialize person contacts."""

    class Meta:
        """Define person contact serialization options."""

        extra_kwargs = {"person": {"required": False}}
        model = models.PersonContact
        fields = "__all__"


class AttachmentSerializer(BaseSerializer):
    """Serialize attachments."""

    class Meta:
        """Define attachment serialization options."""

        model = models.Attachment


class PersonAttachmentSerializer(BaseSerializer):
    """Serialize person attachments."""

    class Meta:
        """Define person attachment serialization options."""

        model = models.PersonAttachment
        exclude = ("person",)


class PersonIDSerializer(BaseSerializer):
    """Serialize person ID records."""

    class Meta:
        """Define person ID serialization options."""

        model = models.PersonID
        exclude = ("person",)


class ConsentSerializer(BaseSerializer):
    """Serialize consent."""

    class Meta:
        """Define consent serialization options."""

        model = models.Consent
        fields = "__all__"


class ConsentTransitionLogSerializer(BaseSerializer):
    """Serialize consent transition."""

    class Meta:
        """Define serialization options."""

        model = models.ConsentTransitionLog
        fields = "__all__"


class OTPVerificationSerializer(serializers.Serializer):
    """Serialize OTP verification input."""

    code = serializers.CharField()


class PersonSerializer(WritabledNestedBaseSerializer):
    """Serialize persons."""

    person_display = serializers.ReadOnlyField(source="get_full_name")
    person_contacts = PersonContactSerializer(
        many=True, required=False, allow_null=True
    )
    consent = ConsentSerializer(read_only=True)
    person_ids = PersonIDSerializer(many=True)
    phone_number = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    id_document_type = serializers.ReadOnlyField(
        source="person_ids.first.id_document_type"
    )
    id_value = serializers.ReadOnlyField(source="person_ids.first.id_value")
    age = serializers.ReadOnlyField()
    global_health_id = serializers.ReadOnlyField()

    def get_phone_number(self, instance: models.Person) -> Optional[str]:
        """Return the first phone number.

        This is being done here to avoid an extra trip to the DB for each
        person during list serialization.
        You MUST ensure that your viewsets prefetch the contacts
        otherwise we'll just be spinning wheels.
        """
        for contact in instance.person_contacts.all():
            if contact.contact_type == "phone_number":
                return contact.contact
        return None

    def get_email(self, instance: models.Person) -> Optional[str]:
        """Return the first email.

        This is being done here to avoid an extra trip to the DB for each
        person during list serialization.
        You MUST ensure that your viewsets prefetch the contacts
        otherwise we'll just be spinning wheels.
        """
        for contact in instance.person_contacts.all():
            if contact.contact_type == "email":
                return contact.contact
        return None

    class Meta:
        """Define person serialization options."""

        model = models.Person
        exclude = ("related_persons",)


class RelatedPersonSerializer(BaseSerializer):
    """Serialize related person."""

    me: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(
        read_only=True
    )
    related = PersonSerializer(read_only=True)
    relationship_display = serializers.SerializerMethodField()

    def get_relationship_display(
        self,
        instance: models.RelatedPerson,
    ) -> str:
        """Return a human-readable version of `relationship`."""
        return RELATIONSHIP_DISPLAYS.get(instance.relationship, "Unknown")

    class Meta:
        """Serialization options."""

        model = models.RelatedPerson
        fields = "__all__"


class LinkPersonSerializer(PersonSerializer):
    """LinkPerson Serializer."""

    relationship = serializers.ChoiceField(RELATIONSHIPS)


class UserProfileSerializer(BaseSerializer):
    """Serialize user profiles."""

    person_id = serializers.ReadOnlyField(source="person.id")
    person_name = serializers.ReadOnlyField(source="person.get_full_name")
    organisation_id = serializers.ReadOnlyField(source="organisation.id")
    organisation_name = serializers.ReadOnlyField(
        source="organisation.organisation_name"
    )

    class Meta:
        """Define serialization options."""

        model = models.UserProfile
        fields = "__all__"


class PractitionerSerializer(WritabledNestedBaseSerializer):
    """Serialize practitioner."""

    person = PersonSerializer()

    class Meta:
        """Define practitioner attachment serialization options."""

        model = models.Practitioner
        fields = "__all__"


class OperatingRegionSerializer(BaseSerializer):
    """Serialize OperatingRegion model."""

    class Meta:
        """Define serialization options."""

        model = models.OperatingRegion
        fields = "__all__"
