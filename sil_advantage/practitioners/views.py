"""Practitioner app views."""

from sil_advantage.common.views.base import BaseView
from sil_advantage.permissions import perms, scopes
from sil_advantage.practitioners.filters import Practitionerfilter
from sil_advantage.practitioners.models import Practitioner
from sil_advantage.practitioners.serializers import PractitionerSerializer


class PractitionerViewSet(BaseView):
    """Practitioner view."""

    permissions = {
        "GET": [perms.PRACTITIONER_VIEW],
        "POST": [perms.PRACTITIONER_CREATE],
        "PATCH": [perms.PRACTITIONER_EDIT],
        "DELETE": [perms.PRACTITIONER_DELETE],
    }

    scopes = {
        "GET": [scopes.PRACTITIONER_READ],
        "POST": [scopes.PRACTITIONER_WRITE],
        "PATCH": [scopes.PRACTITIONER_WRITE],
        "DELETE": [scopes.PRACTITIONER_WRITE],
    }

    queryset = Practitioner.objects.all()
    serializer_class = PractitionerSerializer
    filterset_class = Practitionerfilter
    search_fields = (
        "person__first_name",
        "person__last_name",
        "person__other_names",
        "qualification",
    )

    _data_partition_field = "organisation"
