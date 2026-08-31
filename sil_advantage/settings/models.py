"""Settings models."""
import uuid
from functools import lru_cache
from typing import Any

from django.db import IntegrityError, models

from sil_advantage.common.models import AbstractBase, Organisation
from sil_advantage.common.models.mixins import OrgUnitIdsMixin
from sil_advantage.common.signals import post_instance_save
from sil_advantage.settings import BRANCH_SETTINGS, ORGANISATION_SETTINGS


class OrganisationSetting(AbstractBase, OrgUnitIdsMixin):
    """Model to store organisation settings.

    Names are namespaced per app:
        - "patients:patient_id_format"
        - "sms:appt_reminder_template"
    Preferences are JSONs like:
        - {"value": "MIRAZI/{file_number:04d}/{created:%y}"}
        - {"value": [34,56,12]}
    """

    name = models.CharField(max_length=64, db_index=True)
    preference = models.JSONField()

    _track_settings_history = ("visits:post_visit_survey_template",)

    class Meta(AbstractBase.Meta):
        """Model options."""

        unique_together = [
            ("name", "organisation", "branch_id"),
        ]
        ordering = ("name",)

    def __str__(self) -> str:
        """Get the string representation."""
        return f"{self.name}:{self.value}"

    @property
    def value(self) -> Any:
        """Get actual preference value."""
        return self.preference["value"]

    @classmethod
    def _get_setting_manager(cls, name: str) -> Any:
        """Get the setting manager based on the name."""
        if name in BRANCH_SETTINGS:
            return BRANCH_SETTINGS[name]
        elif name in ORGANISATION_SETTINGS:
            return ORGANISATION_SETTINGS[name]
        else:
            raise ValueError(
                "No setting manager found for setting name: {}".format(name)
            )

    @classmethod
    @lru_cache(maxsize=None)
    def get_default_setting(cls, name: str) -> Any:
        """Return default setting."""
        setting_manager = cls._get_setting_manager(name)
        return setting_manager.default

    @classmethod
    @lru_cache(maxsize=None)
    def get_setting_description(cls, name: str) -> str:
        """Get the setting's description."""
        setting_manager = cls._get_setting_manager(name)
        return setting_manager.description

    @classmethod
    @lru_cache(maxsize=None)
    def get_setting_type(cls, name: str) -> str:
        """Get the setting's type."""
        setting_manager = cls._get_setting_manager(name)
        return setting_manager.type.__name__

    @classmethod
    def validate_setting(cls, name: str, value: Any) -> None:
        """Validate a setting."""
        setting_manager = cls._get_setting_manager(name)
        setting_manager.validate(value)

    @classmethod
    def set_org_setting(
        cls,
        organisation: Organisation | uuid.UUID,
        setting_name: str,
        value: Any = None,
        persist: bool = True,
    ) -> "OrganisationSetting":
        """Set an organisation setting."""
        if value is None:
            value = cls.get_default_setting(setting_name)
        else:
            cls.validate_setting(setting_name, value)

        if isinstance(organisation, uuid.UUID):
            organisation = Organisation.objects.get(pk=organisation)

        payload = {
            "name": setting_name,
            "preference": {"value": value},
            "organisation": organisation,
            "created_by": organisation.created_by,
            "updated_by": organisation.updated_by,
        }

        if persist:
            try:
                setting, _ = cls.objects.update_or_create(
                    name=setting_name,
                    organisation=organisation,
                    branch_id=None,
                    defaults=payload,
                    created_by=organisation.created_by,
                    updated_by=organisation.updated_by,
                )
                cls.get_org_setting.cache_clear()

                if setting_name in cls._track_settings_history:
                    post_instance_save.send_robust(
                        cls,
                        organisation=organisation,
                        instance_id=setting.id,
                        snapshot=value,
                        created_by=organisation.created_by,
                        updated_by=organisation.updated_by,
                    )
            except IntegrityError:
                raise ValueError(f"Multiple settings found for {setting_name}")
        else:
            setting = cls(**payload)

        return setting

    @classmethod
    def set_branch_setting(
        cls,
        organisation: Organisation,
        branch_id: Any | None,
        setting_name: str,
        value: Any = None,
        persist: bool = True,
    ) -> "OrganisationSetting":
        """Set a branch setting."""
        if value is None:
            value = cls.get_default_setting(setting_name)
        else:
            cls.validate_setting(setting_name, value)

        payload = {
            "name": setting_name,
            "preference": {"value": value},
            "organisation": organisation,
            "branch_id": branch_id,
            "created_by": organisation.created_by,
            "updated_by": organisation.updated_by,
        }

        if persist:
            setting, _ = cls.objects.update_or_create(
                name=setting_name,
                organisation=organisation,
                branch_id=branch_id,
                defaults=payload,
                created_by=organisation.created_by,
                updated_by=organisation.updated_by,
            )
            cls.get_branch_setting.cache_clear()

        else:
            setting = cls(**payload)
        return setting

    @classmethod
    @lru_cache(maxsize=10_000)
    def get_org_setting(
        cls,
        organisation: Organisation | uuid.UUID,
        setting_name: str,
    ) -> "OrganisationSetting":
        """Get or set an organisation setting."""
        try:
            return cls.objects.filter(
                name=setting_name,
                organisation=organisation,
            ).latest("updated")
        except cls.DoesNotExist:
            return cls.set_org_setting(organisation, setting_name)

    @classmethod
    @lru_cache(maxsize=10_000)
    def get_branch_setting(
        cls,
        organisation: Organisation,
        branch_id: str,
        setting_name: str,
    ) -> "OrganisationSetting":
        """Get or set a branch setting."""
        try:
            return cls.objects.filter(
                name=setting_name,
                organisation=organisation,
                branch_id=branch_id,
            ).latest("updated")
        except cls.DoesNotExist:
            return cls.set_branch_setting(organisation, branch_id, setting_name)

    @classmethod
    @lru_cache(maxsize=10_000)
    def get_setting(
        cls,
        organisation: Organisation | uuid.UUID,
        branch_id: str,
        setting_name: str,
    ) -> "OrganisationSetting":
        """Get a setting from branch if available, otherwise from organisation."""
        # Check if setting is available in branch settings
        if setting_name in BRANCH_SETTINGS:
            try:
                return cls.objects.filter(
                    name=setting_name,
                    organisation=organisation,
                    branch_id=branch_id,
                ).latest("updated")
            except cls.DoesNotExist:
                pass

        # Fallback to organisation setting
        return cls.get_org_setting(organisation, setting_name)

    @classmethod
    def all_org_settings(
        cls,
        organisation: Organisation,
    ) -> models.QuerySet["OrganisationSetting"]:
        """Return all settings for a certain organisation."""
        saved_settings = cls.objects.filter(
            organisation=organisation, branch_id__isnull=True
        ).order_by()
        possible_settings = set(ORGANISATION_SETTINGS.keys())

        missing_settings = possible_settings - set(
            saved_settings.values_list("name", flat=True)
        )
        settings_to_save = []
        for name in missing_settings:
            settings_to_save.append(
                cls.set_org_setting(
                    organisation,
                    name,
                    persist=False,
                )
            )

        if len(settings_to_save) > 0:
            cls.objects.bulk_create(settings_to_save)
            cls.get_org_setting.cache_clear()

        return cls.objects.filter(
            organisation=organisation, branch_id__isnull=True
        ).order_by()

    @classmethod
    def all_branch_settings(
        cls,
        organisation: Organisation,
        branch_id: Any | None,
    ) -> models.QuerySet["OrganisationSetting"]:
        """Return all branch settings."""
        saved_settings = cls.objects.filter(
            organisation=organisation,
            branch_id=branch_id,
        ).order_by()
        possible_settings = set(BRANCH_SETTINGS.keys())

        # Check if there are any missing settings
        missing_settings = possible_settings - set(
            saved_settings.values_list("name", flat=True)
        )
        settings_to_save = []
        for name in missing_settings:
            settings_to_save.append(
                cls.set_branch_setting(
                    organisation,
                    branch_id,
                    name,
                    persist=False,
                )
            )
        if len(settings_to_save) > 0:
            cls.objects.bulk_create(settings_to_save)
            cls.get_branch_setting.cache_clear()
        return cls.objects.filter(
            organisation=organisation, branch_id=branch_id
        ).order_by()
