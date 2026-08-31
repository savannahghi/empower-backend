"""Sample serializers."""

from sil_advantage.common.serializers import BaseSerializer

from . import models


class ABCSerializer(BaseSerializer):
    """Sample Serializer."""

    class Meta:
        """Serializer options."""

        model = models.ABC
        fields = "__all__"


class ABCDetailSerializer(ABCSerializer):
    """Sample Detail Serializer."""

    pass
