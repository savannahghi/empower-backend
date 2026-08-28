"""Notifications views."""
from sil_advantage.common.filters.base import CommonFieldsFilterset, ListFilter
from sil_advantage.notifications.models import Group, GroupMember


class GroupFilter(CommonFieldsFilterset):
    """Group filter."""

    role = ListFilter()

    class Meta:
        """Filter options."""

        model = Group
        fields = "__all__"


class GroupMemberFilter(CommonFieldsFilterset):
    """GroupMember filter."""

    class Meta:
        """Filter options."""

        model = GroupMember
        fields = "__all__"
