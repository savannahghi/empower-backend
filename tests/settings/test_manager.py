"""Test setting manager."""
import re

import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase

from sil_advantage.settings.manager import SettingManager


class SettingManagerTestCase(TestCase):
    """Test setting manager."""

    def test_validate_default_happy_case(self):
        """Test validating the default value."""
        manager = SettingManager(
            "sms:send_sms",
            "Send SMS?",
            True,
            bool,
        )

        assert manager.validate(False) is True

    def test_validate_bad_data_type(self):
        """Test validation with a bad data type."""
        expected_msg = re.escape(
            "Preference has invalid type <class 'str'>, " "expecting <class 'bool'>."
        )
        with pytest.raises(TypeError, match=expected_msg):
            SettingManager(
                "sms:send_sms",
                "Send SMS?",
                "No",
                bool,
            )

    def test_validate_with_validator_failure(self):
        """Test validation with developer provided validator."""
        expected_msg = re.escape("Preference validation failed.")
        with pytest.raises(ValidationError, match=expected_msg):
            SettingManager(
                "common:preferred_contact_method",
                "My Preferred Contact Method",
                "whatsapp",
                str,
                lambda x: x in ("sms", "email"),
            )
