"""serializers for the test app."""
from rest_framework import serializers

from .models import CustomMeta, MtoMCustomMeta, TestCustom


class CustomMetaSerializer(serializers.ModelSerializer):
    """Serializer class for CustomMeta model."""

    class Meta:
        """Define model name and fields."""

        model = CustomMeta
        fields = "__all__"


class MtoMCustomMetaSerializer(serializers.ModelSerializer):
    """Serializer class for MtoMCustomMeta model."""

    custom_metas = CustomMetaSerializer(many=True)

    class Meta:
        """Define model name and fields."""

        model = MtoMCustomMeta
        fields = "__all__"


class TestCustomSerializer(serializers.ModelSerializer):
    """Seriaizer class for TestCustom model."""

    class Meta:
        """Define model name and fields."""

        model = TestCustom
        fields = "__all__"
