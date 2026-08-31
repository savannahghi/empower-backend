"""Notifications serializers."""
from sil_advantage.common.serializers import BaseSerializer, PersonSerializer
from sil_advantage.notifications.models import Group, GroupMember


class GroupMemberSerializer(BaseSerializer):
    """GroupMember Serializer."""

    person = PersonSerializer(read_only=True)

    class Meta:
        """Serialization options."""

        model = GroupMember
        fields = "__all__"


class GroupSerializer(BaseSerializer):
    """Group Serializer."""

    members = GroupMemberSerializer(many=True, required=False)

    class Meta:
        """Serialization options."""

        model = Group
        fields = "__all__"
