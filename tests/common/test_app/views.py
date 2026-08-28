"""Views for the test app."""
from rest_framework import views
from rest_framework.generics import ListCreateAPIView
from rest_framework.permissions import AllowAny

from .models import CustomMeta, MtoMCustomMeta, TestCustom
from .serializers import CustomMetaSerializer, MtoMCustomMetaSerializer


class CustomMetaView(ListCreateAPIView):
    """View for the CustomMeta model."""

    permission_classes = (AllowAny,)
    queryset = CustomMeta.objects.all()
    serializer_class = CustomMetaSerializer


class MtoMCustomMetaView(ListCreateAPIView):
    """View for the MtoMcustomMeta model."""

    permission_classes = (AllowAny,)
    queryset = MtoMCustomMeta.objects.all()
    serializer_class = MtoMCustomMetaSerializer


class TestCustomView(views.APIView):
    """View for the TestCustom model."""

    permission_classes = (AllowAny,)
    queryset = TestCustom.objects.all()
    metadata_class = None
