"""Settings serializers."""
from typing import Any

from rest_framework import serializers

from sil_advantage.common.models import Organisation
from sil_advantage.common.serializers import BaseSerializer
from sil_advantage.settings.models import OrganisationSetting


class OrganisationSettingSerializer(BaseSerializer):
    """Organisation Setting Serializer."""

    default = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    setting_type = serializers.SerializerMethodField()
    preference = serializers.JSONField(read_only=True)

    def get_default(self, instance: Organisation) -> Any:
        """Get default preference for this setting."""
        return OrganisationSetting.get_default_setting(instance.name)

    def get_description(self, instance: Organisation) -> str:
        """Get the setting's description."""
        return OrganisationSetting.get_setting_description(instance.name)

    def get_setting_type(self, instance: Organisation) -> str:
        """Get the setting's type."""
        return OrganisationSetting.get_setting_type(instance.name)

    def to_representation(
        self,
        instance: Organisation,
    ) -> dict[str, Any]:
        """Customize representation."""
        data = super().to_representation(instance)
        data["value"] = data["preference"]["value"]
        data.pop("preference")
        return data

    class Meta:
        """Serialization options."""

        model = OrganisationSetting
        exclude = ("active",)
