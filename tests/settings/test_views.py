"""Test setting models."""
from django.urls import reverse

from sil_advantage.settings.models import OrganisationSetting
from tests.common.test_common_views import LoggedInMixin


class OrgSettingViewTestCase(LoggedInMixin):
    """Test organisation setting view."""

    url = reverse("org_settings")
    branch_url = reverse("branch_settings")

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        branch_id = "f249c5e2-d4b9-4a24-8ce2-83451aeb837e"

        OrganisationSetting.set_org_setting(
            self.global_organisation,
            "patients:patient_id_format",
            "MIRAZI/{file_number:04d}/{created:%y}",
        )
        OrganisationSetting.set_org_setting(
            self.global_organisation,
            "sms:appointment_reminder_en_template",
        )
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

    def test_get_all_org_settings(self):
        """Test getting all organisation settings."""
        result = self.client.get(self.url).json()
        assert len(result) == 26

        # test idempotency
        result = self.client.get(self.url).json()
        assert len(result) == 26

    def test_get_all_branch_settings(self):
        """Test getting all branch settings."""
        branch_id = "f249c5e2-d4b9-4a24-8ce2-83451aeb837e"
        headers = {"HTTP_X_BRANCH": branch_id}
        response = self.client.get(self.branch_url, **headers)

        self.assertEqual(len(response.data), 13)

        # test idempotency
        result = self.client.get(self.branch_url, **headers).json()
        assert len(result) == 13

    def test_updating_branch_setting(self):
        """Test updating a branch setting."""
        result = self.client.patch(
            self.branch_url,
            [
                {
                    "name": "billing:promotional_sender_id",
                    "value": "BeWellInfo1",
                }
            ],
        )

        setting = next(
            setting
            for setting in result.json()
            if setting["name"] == "billing:promotional_sender_id"
        )
        assert setting["value"] == "BeWellInfo1"
        assert setting["description"] == "Promotional Sender ID"
        assert setting["setting_type"] == "str"

    def test_updating_org_setting(self):
        """Test updating an organisation setting."""
        result = self.client.patch(
            self.url,
            [
                {
                    "name": "patients:patient_id_format",
                    "value": "OREGON/{file_number:04d}",
                }
            ],
        )

        setting = next(
            setting
            for setting in result.json()
            if setting["name"] == "patients:patient_id_format"
        )
        assert setting["value"] == "OREGON/{file_number:04d}"
        assert setting["description"] == "Patient ID Format"
        assert setting["setting_type"] == "str"
