"""Prescription app views."""
from sil_advantage.common.views.base import BaseView
from sil_advantage.permissions import perms, scopes
from sil_advantage.prescriptions.filters import PrescriptionFilter
from sil_advantage.prescriptions.models import Prescription
from sil_advantage.prescriptions.serializers import PrescriptionSerializer


class PrescriptionViewSet(BaseView):
    """Prescription viewset."""

    permissions = {
        "GET": [perms.MESSAGE_TEMPLATE_VIEW],
        "POST": [perms.MESSAGE_TEMPLATE_CREATE],
        "PATCH": [perms.MESSAGE_TEMPLATE_EDIT],
        "DELETE": [perms.MESSAGE_TEMPLATE_DELETE],
    }
    scopes = {
        "GET": [scopes.MESSAGE_TEMPLATE_READ],
        "POST": [scopes.MESSAGE_TEMPLATE_WRITE],
        "PATCH": [scopes.MESSAGE_TEMPLATE_WRITE],
        "DELETE": [scopes.MESSAGE_TEMPLATE_WRITE],
    }

    queryset = Prescription.objects.all()
    serializer_class = PrescriptionSerializer
    filterset_class = PrescriptionFilter
    _prefetch_related = ["dosages"]
