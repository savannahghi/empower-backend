"""Practitioner app serializers."""
from sil_advantage.common.serializers.base import WritabledNestedBaseSerializer
from sil_advantage.common.serializers.common_serializers import PersonSerializer
from sil_advantage.practitioners.models import Practitioner


class PractitionerSerializer(WritabledNestedBaseSerializer):
    """Serialize practitioner."""

    person = PersonSerializer()

    class Meta:
        """Define practitioner attachment serialization options."""

        model = Practitioner
        fields = "__all__"
