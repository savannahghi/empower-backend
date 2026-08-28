"""Test setting models."""
from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError
from django.utils import timezone

from sil_advantage.common.models import InstanceHistory
from sil_advantage.settings.models import OrganisationSetting
from tests.common.test_common_views import LoggedInMixin


class OrgSettingModelTestCase(LoggedInMixin):
    """Test organisation setting model."""

    def test_setting_org_setting(self):
        """Test setting and reading org setting."""
        org_setting = OrganisationSetting.set_org_setting(
            self.global_organisation,
            "sms:appointment_reminder_en_template",
            "Heyo {fname}!",
        )
        assert org_setting.value == "Heyo {fname}!"
        assert str(org_setting) == (
            "sms:appointment_reminder_en_template:" "Heyo {fname}!"
        )

    @patch.object(OrganisationSetting, "objects")
    def test_set_org_setting_raises_value_error_on_duplicate_setting(
        self, mock_objects
    ):
        """Test that set_org_setting raises ValueError on duplicate setting."""
        mock_objects.update_or_create.side_effect = IntegrityError("Duplicate setting")

        with self.assertRaises(ValueError) as context:
            OrganisationSetting.set_org_setting(
                self.global_organisation,
                "sms:appointment_reminder_en_template",
                "Attempted Duplicate Value",
            )

        self.assertIn(
            "Multiple settings found for sms:appointment_reminder_en_template",
            str(context.exception),
        )

    def test_setting_branch_setting(self):
        """Test setting and reading branch setting."""
        branch_id = "f249c5e2-d4b9-4a24-8ce2-83451aeb837e"
        branch_setting = OrganisationSetting.set_branch_setting(
            self.global_organisation,
            branch_id,
            "billing:promotional_sender_id",
            "BeWellInfo",
        )
        assert branch_setting.value == "BeWellInfo"
        assert str(branch_setting) == ("billing:promotional_sender_id:" "BeWellInfo")

    def test_getting_the_default_value(self):
        """Test getting the default value."""
        default = OrganisationSetting.get_default_setting(
            "patients:patient_id_format",
        )
        assert default == "{file_number}"

    def test_getting_branch_setting_default_value(self):
        """Test getting the default value."""
        default = OrganisationSetting.get_default_setting(
            "billing:promotional_sender_id",
        )
        assert default == "Slade360Adv"

    def test_getting_the_default_value_no_name(self):
        """Test getting the default value where name does not exist."""
        with self.assertRaises(ValueError):
            OrganisationSetting.get_default_setting("patients:patient_id_format2")

    def test_getting_the_setting_description(self):
        """Test getting the settings description."""
        description = OrganisationSetting.get_setting_description(
            "patients:patient_id_format"
        )
        assert description == "Patient ID Format"

    def test_getting_one_branch_setting(self):
        """Test getting a single setting."""
        branch_id = "f249c5e2-d4b9-4a24-8ce2-83451aeb837e"
        setting = OrganisationSetting.get_branch_setting(
            self.global_organisation,
            branch_id,
            "billing:promotional_sender_id",
        )
        assert setting.value == "Slade360Adv"

        # test idempotency
        setting = OrganisationSetting.get_branch_setting(
            self.global_organisation,
            branch_id,
            "billing:promotional_sender_id",
        )
        assert setting.value == "Slade360Adv"

    def test_getting_one_setting(self):
        """Test getting a single setting."""
        setting = OrganisationSetting.get_org_setting(
            self.global_organisation,
            "patients:patient_id_format",
        )
        assert setting.value == "{file_number}"

        # test idempotency
        setting = OrganisationSetting.get_org_setting(
            self.global_organisation,
            "patients:patient_id_format",
        )
        assert setting.value == "{file_number}"

    def test_get_all_branch_settings(self):
        """Test getting all branch settings."""
        branch_id = "f249c5e2-d4b9-4a24-8ce2-83451aeb837e"
        branch_id2 = "117b7f08-8b97-49aa-920e-e846e79b5ea3"
        OrganisationSetting.set_branch_setting(
            self.global_organisation,
            branch_id,
            "billing:promotional_sender_id",
            "BeWellInfo",
        )
        OrganisationSetting.set_branch_setting(
            self.global_organisation,
            branch_id,
            "billing:transactional_sender_id",
        )
        OrganisationSetting.set_branch_setting(
            self.global_organisation,
            branch_id2,
            "billing:promotional_sender_id",
            "AnotherSenderID",
        )
        OrganisationSetting.set_branch_setting(
            self.global_organisation,
            branch_id2,
            "billing:transactional_sender_id",
        )

        all_settings = OrganisationSetting.all_branch_settings(
            self.global_organisation, branch_id
        )
        all_settings2 = OrganisationSetting.all_branch_settings(
            self.global_organisation, branch_id2
        )
        assert len(all_settings) == 13
        assert len(all_settings2) == 13
        assert all_settings2[0].value == "AnotherSenderID"
        assert all_settings[0].value == "BeWellInfo"

        # test idempotency
        all_settings = OrganisationSetting.all_branch_settings(
            self.global_organisation, branch_id
        )
        assert len(all_settings) == 13

    def test_get_all_organisation_settings(self):
        """Test getting all organisation settings."""
        OrganisationSetting.set_org_setting(
            self.global_organisation,
            "patients:patient_id_format",
            "MIRAZI/{file_number:04d}/{created:%y}",
        )
        OrganisationSetting.set_org_setting(
            self.global_organisation,
            "sms:appointment_reminder_en_template",
        )

        all_settings = OrganisationSetting.all_org_settings(
            self.global_organisation,
        )
        assert len(all_settings) == 26

        # test idempotency
        all_settings = OrganisationSetting.all_org_settings(
            self.global_organisation,
        )
        assert len(all_settings) == 26

    def test_tracking_post_visit_survey_template_history(self):
        """Test tracking post visit survey template history."""
        org = self.global_organisation
        kesho = timezone.now() + timedelta(days=1)

        OrganisationSetting.all_org_settings(org)
        setting = OrganisationSetting.get_org_setting(
            org,
            "visits:post_visit_survey_template",
        )
        template = InstanceHistory.as_of(
            OrganisationSetting,
            setting.id,
            kesho,
        )
        assert template is None

        OrganisationSetting.set_org_setting(
            org,
            "visits:post_visit_survey_template",
            [{"foo": "bar"}],
        )
        assert InstanceHistory.as_of(OrganisationSetting, setting.id, kesho) == [
            {"foo": "bar"}
        ]

        # test idempotency
        OrganisationSetting.set_org_setting(
            org,
            "visits:post_visit_survey_template",
            [{"foo": "bar"}],
        )
        assert InstanceHistory.objects.count() == 1
