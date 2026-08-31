"""Notifications views."""
from sil_advantage.common.views.base import CacheableBaseView
from sil_advantage.notifications.filters import GroupFilter, GroupMemberFilter
from sil_advantage.notifications.models import Group, GroupMember
from sil_advantage.notifications.serializers import (
    GroupMemberSerializer,
    GroupSerializer,
)
from sil_advantage.permissions import perms, scopes


class GroupViewSet(CacheableBaseView):
    """Group viewset."""

    permissions = {
        "GET": [perms.GROUP_VIEW],
        "POST": [perms.GROUP_CREATE],
        "PATCH": [perms.GROUP_EDIT],
        "DELETE": [perms.GROUP_DELETE],
    }
    scopes = {
        "GET": [scopes.GROUP_READ],
        "POST": [scopes.GROUP_WRITE],
        "PATCH": [scopes.GROUP_WRITE],
        "DELETE": [scopes.GROUP_WRITE],
    }

    queryset = Group.objects.all()
    _select_related = []
    _prefetch_related = []
    serializer_class = GroupSerializer

    filterset_class = GroupFilter

    _data_partition_field = "organisation"


class GroupMemberViewSet(CacheableBaseView):
    """Group Member viewset."""

    permissions = {
        "GET": [perms.GROUP_VIEW],
        "POST": [perms.GROUP_CREATE],
        "PATCH": [perms.GROUP_EDIT],
        "DELETE": [perms.GROUP_DELETE],
    }
    scopes = {
        "GET": [scopes.GROUP_READ],
        "POST": [scopes.GROUP_WRITE],
        "PATCH": [scopes.GROUP_WRITE],
        "DELETE": [scopes.GROUP_WRITE],
    }

    queryset = GroupMember.objects.all()
    _select_related = []
    _prefetch_related = []
    serializer_class = GroupMemberSerializer

    filterset_class = GroupMemberFilter

    _data_partition_field = "organisation"
